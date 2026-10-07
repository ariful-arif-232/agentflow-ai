"""Rebalancing Policy V2 — cost-aware, uncertainty-aware, safety-first.

V1 (``rebalance.recommend``) is kept unchanged. V2 keeps every V1 hard constraint
(HIGH/CRITICAL recipients, anomalous recipients held for review, LOW-risk non-anomalous
donors, same district, <= 15 km, BDT 500 steps, BDT 2,000 minimum, <= 2 donors per
recipient, distributor escalation, simulation-only approval) and changes four things:

1. **Recipient target** — bring cash to ``P50 + λ·(P90 − P50)`` instead of always P90
   (λ = ``target_quantile_weight``). Optionally only support recipients whose cash is
   below even the P50 forecast (``require_p50_shortfall``).

2. **Dynamic donor protected reserve** — never weaker than V1:

   ``reserve = max(BDT 5,000, 1.10·P90, (P90 + u·(P90 − P50)) · vel_factor · hist_factor)``

   with ``vel_factor = 1 + 0.5·clip(velocity_ratio_3h − 1, 0, 1)`` and
   ``hist_factor = 1 + 0.5·clip(hist_shortage_rate / 0.15, 0, 1)``. A donor busier than
   usual, or with a history of shortages, keeps more cash. After the *complete* plan the
   donor must still be LOW risk.

3. **Minimum-benefit gate** — a transfer leg is only recommended if, for the recipient, it
   (a) lowers the risk level by at least one level, or (b) lowers the risk score by at
   least ``min_risk_drop`` points, or (c) removes at least half of the P50 expected
   shortfall. Otherwise the need is escalated instead of moving a token amount.

4. **Benefit–cost–safety ranking** of candidate donors (lexicographic, inspectable):
   (i) donors that can cover the remaining need alone first (fewer legs), then
   (ii) highest recipient risk-points removed per BDT 100 of logistics cost, then
   (iii) largest donor margin above its reserve after the transfer, then (iv) distance.

   The cost in (ii) is set by ``ranking_cost_model``. ``"phase1_simple"`` (BDT 150 + BDT 25/km) is the
   **serving default**: it is the ranking behind the published Phase-1 evidence. ``"logistics_proxy"``
   ranks by the total of the Phase-2 synthetic operational cost proxy in ``logistics.py``; it is a
   Phase-2 *experiment* that did not improve held-out outcomes (1,229 vs 1,223 shortage events), so it
   is only used when requested explicitly. Either way every transfer is still *costed* with the
   Phase-2 proxy (``logistics_cost``). Cost only ranks candidates that already passed every safety
   check — it never relaxes a constraint.

``target_quantile_weight``, ``donor_uncertainty_mult``, ``min_risk_drop`` and
``require_p50_shortfall`` are selected on chronological policy-validation folds inside
the training period (see ``policy_selection.py``); the held-out test period is never used
for selection. The fixed design constants (velocity/history weights 0.5, 50% shortfall
cut, LOW-after-plan) were set a priori.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, fields

import numpy as np
import pandas as pd

from . import config, logistics, risk
from .rebalance import TRIGGER_LEVELS, _risk_for, haversine_km, logistics_summary

SELECTION_PATH = config.ARTIFACTS_DIR / "policy_selection.json"


RANKING_COST_MODELS = ("phase1_simple", "logistics_proxy")
SERVING_RANKING_COST_MODEL = "phase1_simple"
EXPERIMENT_RANKING_COST_MODEL = "logistics_proxy"


@dataclass(frozen=True)
class RebalanceV2Config:
    # --- hard operational constraints shared with V1 ---
    max_distance_km: float = 15.0
    donor_min_floor: float = 5_000.0
    v1_buffer_ratio: float = 1.10
    min_transfer: float = 2_000.0
    round_to: float = 500.0
    max_donors_per_recipient: int = 2
    cost_fixed_bdt: float = 150.0
    cost_per_km_bdt: float = 25.0
    # --- tunable: selected on training-period policy-validation folds only ---
    target_quantile_weight: float = 1.0
    donor_uncertainty_mult: float = 0.5
    min_risk_drop: float = 10.0
    require_p50_shortfall: bool = False
    # --- fixed a-priori design constants ---
    velocity_reserve_weight: float = 0.5
    history_reserve_weight: float = 0.5
    history_scale: float = 0.15
    min_shortfall_cut_frac: float = 0.5
    donor_max_level_after: str = "LOW"
    # --- which cost the donor ranking divides by. Serving default: the proven Phase-1 ranking.
    #     "logistics_proxy" is the Phase-2 ranking experiment and must be requested explicitly. ---
    ranking_cost_model: str = "phase1_simple"

    def __post_init__(self) -> None:
        if self.ranking_cost_model not in RANKING_COST_MODELS:
            raise ValueError(f"ranking_cost_model must be one of {RANKING_COST_MODELS}")

    @classmethod
    def tunable_fields(cls) -> tuple[str, ...]:
        return ("target_quantile_weight", "donor_uncertainty_mult", "min_risk_drop", "require_p50_shortfall")


def selected_config() -> RebalanceV2Config:
    """V2 config with the parameters chosen on policy-validation folds (artifact), else defaults."""
    if SELECTION_PATH.exists():
        chosen = json.loads(SELECTION_PATH.read_text()).get("selected_config", {})
        # The ranking cost used while *selecting* parameters (Phase-1 protocol) is not the serving choice.
        allowed = {f.name for f in fields(RebalanceV2Config)} - {"ranking_cost_model"}
        return RebalanceV2Config(**{k: v for k, v in chosen.items() if k in allowed})
    return RebalanceV2Config()


def donor_reserve(p50, p90, velocity_ratio, hist_rate, cfg: RebalanceV2Config):
    """Dynamic donor protected reserve (vectorised). Never weaker than the V1 protected level."""
    p50 = np.maximum(np.asarray(p50, float), 0.0)
    p90 = np.maximum(np.asarray(p90, float), p50)
    vel = np.nan_to_num(np.asarray(velocity_ratio, float), nan=1.0)
    hist = np.nan_to_num(np.asarray(hist_rate, float), nan=0.0)
    vel_factor = 1.0 + cfg.velocity_reserve_weight * np.clip(vel - 1.0, 0.0, 1.0)
    hist_factor = 1.0 + cfg.history_reserve_weight * np.clip(hist / cfg.history_scale, 0.0, 1.0)
    dynamic = (p90 + cfg.donor_uncertainty_mult * (p90 - p50)) * vel_factor * hist_factor
    return np.maximum.reduce([np.full_like(p90, cfg.donor_min_floor), cfg.v1_buffer_ratio * p90, dynamic])


def recipient_target(p50, p90, cfg: RebalanceV2Config):
    p50 = np.maximum(np.asarray(p50, float), 0.0)
    p90 = np.maximum(np.asarray(p90, float), p50)
    return p50 + cfg.target_quantile_weight * (p90 - p50)


def leg_benefit(cash_before: float, amount: float, p50: float, p90: float, vel: float, hist: float) -> dict:
    """Recipient benefit of adding ``amount`` to ``cash_before`` (deterministic, from the risk formula)."""
    s0, l0 = risk.risk_scalar(cash_before, p50, p90, vel, hist)
    s1, l1 = risk.risk_scalar(cash_before + amount, p50, p90, vel, hist)
    sf0 = max(p50 - cash_before, 0.0)
    sf1 = max(p50 - cash_before - amount, 0.0)
    cov0 = cash_before / p90 if p90 >= risk.MIN_REQUIREMENT else None
    cov1 = (cash_before + amount) / p90 if p90 >= risk.MIN_REQUIREMENT else None
    return {"risk_score_before": s0, "risk_score_after": s1, "risk_level_before": l0, "risk_level_after": l1,
            "risk_drop": round(s0 - s1, 1), "levels_dropped": risk.LEVEL_RANK[l0] - risk.LEVEL_RANK[l1],
            "shortfall_before": sf0, "shortfall_after": sf1, "shortfall_reduction": sf0 - sf1,
            "p90_coverage_before": cov0, "p90_coverage_after": cov1}


def passes_gate(b: dict, cfg: RebalanceV2Config) -> tuple[bool, str]:
    if b["levels_dropped"] >= 1:
        return True, f"lowers risk from {b['risk_level_before']} to {b['risk_level_after']}"
    if b["risk_drop"] >= cfg.min_risk_drop:
        return True, f"cuts the risk score by {b['risk_drop']:.0f} points"
    if b["shortfall_before"] > 0 and b["shortfall_reduction"] >= cfg.min_shortfall_cut_frac * b["shortfall_before"]:
        return True, f"removes {100 * b['shortfall_reduction'] / b['shortfall_before']:.0f}% of the expected shortfall"
    return False, "benefit below the minimum-benefit gate"


def ranking_cost(dist: float, amount: float, cfg: RebalanceV2Config, lcfg: logistics.LogisticsCostConfig) -> float:
    if cfg.ranking_cost_model == "phase1_simple":
        return logistics.phase1_simple_cost(dist, cfg.cost_fixed_bdt, cfg.cost_per_km_bdt)
    return logistics.transfer_cost_total(dist, amount, lcfg)


def recommend_v2(snap: pd.DataFrame, cfg: RebalanceV2Config | None = None, with_details: bool = True,
                 logistics_cfg: logistics.LogisticsCostConfig | None = None) -> dict:
    """Same output schema as V1 ``rebalance.recommend`` plus V2 evidence fields."""
    cfg = cfg or selected_config()
    lcfg = logistics_cfg or logistics.DEFAULT_CONFIG
    s = snap.set_index("agent_id", drop=False)
    ids = list(s.index)
    cash = s["cash_balance"].astype(float).to_dict()
    p50 = s["pred_net_requirement_6h"].astype(float).clip(lower=0).to_dict()
    p90 = np.maximum(s["pred_net_requirement_p90_6h"].astype(float), s["pred_net_requirement_6h"].astype(float).clip(lower=0))
    p90 = p90.to_dict()
    vel = s["velocity_ratio_3h"].astype(float).fillna(1.0).to_dict()
    hist = s["hist_shortage_rate"].astype(float).fillna(0.0).to_dict()
    anomalous = (s["anomaly_status"] == "ANOMALOUS").to_dict()
    reserve = dict(zip(ids, donor_reserve(s["pred_net_requirement_6h"], s["pred_net_requirement_p90_6h"],
                                          s["velocity_ratio_3h"], s["hist_shortage_rate"], cfg)))
    surplus = {a: max(cash[a] - reserve[a], 0.0) for a in ids}
    donor_ok = {a: (s.at[a, "risk_level"] == "LOW") and not anomalous[a] and surplus[a] >= cfg.min_transfer for a in ids}
    remaining = {a: (surplus[a] if donor_ok[a] else 0.0) for a in ids}
    lat = s["synthetic_latitude"].astype(float).to_dict()
    lon = s["synthetic_longitude"].astype(float).to_dict()
    district = s["district"].astype(str).to_dict()
    by_district: dict[str, list[str]] = {}
    for a in ids:
        by_district.setdefault(district[a], []).append(a)

    recs, escalations, held = [], [], []
    gate_rejections = 0
    recipients = s[s["risk_level"].isin(TRIGGER_LEVELS)].sort_values(["risk_score", "expected_shortfall"], ascending=False)
    for rid in recipients.index:
        target = float(recipient_target(p50[rid], p90[rid], cfg))
        need = max(target - cash[rid], 0.0)
        if need < cfg.min_transfer:
            continue
        if cfg.require_p50_shortfall and cash[rid] >= p50[rid]:
            continue  # risk driven only by the tail scenario: monitor, no transfer
        if anomalous[rid]:
            held.append({"agent_id": rid, "risk_score": float(s.at[rid, "risk_score"]), "need": round(need, 0),
                         "reason": "Behavioural anomaly detected — manual review required before any liquidity support."})
            continue
        used = 0
        rejected_any = False
        while used < cfg.max_donors_per_recipient and need >= cfg.min_transfer:
            cands = []
            for did in by_district[district[rid]]:
                if did == rid or remaining[did] < cfg.min_transfer:
                    continue
                dist = float(haversine_km(lat[rid], lon[rid], lat[did], lon[did]))
                if dist > cfg.max_distance_km:
                    continue
                amount = float(np.floor(min(need, remaining[did]) / cfg.round_to) * cfg.round_to)
                if amount < cfg.min_transfer:
                    continue
                b = leg_benefit(cash[rid], amount, p50[rid], p90[rid], vel[rid], hist[rid])
                ok, why = passes_gate(b, cfg)
                if not ok:
                    rejected_any = True
                    continue
                d_score, d_level = risk.risk_scalar(cash[did] - amount, p50[did], p90[did], vel[did], hist[did])
                if risk.LEVEL_RANK[d_level] > risk.LEVEL_RANK[cfg.donor_max_level_after]:
                    continue
                cost = ranking_cost(dist, amount, cfg, lcfg)
                margin_after = cash[did] - amount - reserve[did]
                covers = amount >= need - cfg.round_to + 1e-9
                key = (0 if covers else 1, -round(100.0 * b["risk_drop"] / cost, 3),
                       -round(margin_after / max(reserve[did], 1.0), 3), dist, did)
                cands.append((key, did, amount, dist, cost, b, why, d_score, d_level))
            if not cands:
                break
            key, did, amount, dist, cost, b, why, d_score, d_level = min(cands, key=lambda c: c[0])
            cash[did] -= amount
            cash[rid] += amount
            remaining[did] -= amount
            need -= amount
            used += 1
            recs.append({
                "id": f"RB-{len(recs) + 1:03d}", "policy": "v2",
                "source_agent": did, "destination_agent": rid, "recommended_amount": amount,
                "district": district[rid], "distance_km": round(dist, 2),
                "estimated_cost_bdt": round(logistics.phase1_simple_cost(dist, cfg.cost_fixed_bdt, cfg.cost_per_km_bdt), 0),
                "logistics_cost": logistics.transfer_cost(dist, amount, lcfg), "donor_rank": used,
                "expected_benefit": {"risk_score_before": b["risk_score_before"], "risk_score_after": b["risk_score_after"],
                                     "risk_level_before": b["risk_level_before"], "risk_level_after": b["risk_level_after"],
                                     "shortfall_reduction_bdt": round(b["shortfall_reduction"], 0), "gate_reason": why},
                "candidate_rank_key": {"covers_remaining_need": key[0] == 0,
                                       "risk_points_per_bdt100_cost": -key[1],
                                       "donor_margin_ratio_after": -key[2], "distance_km": round(dist, 2),
                                       "ranking_cost_bdt": round(cost, 2), "ranking_cost_model": cfg.ranking_cost_model},
            })
        if rejected_any and used == 0:
            gate_rejections += 1
        if need >= cfg.min_transfer:
            reason = ("No peer transfer passes the minimum-benefit and donor-safety checks — escalate to distributor "
                      "replenishment." if rejected_any and used == 0 else
                      "No eligible peer surplus within range — escalate to distributor replenishment.")
            unresolved = float(np.ceil(need / cfg.round_to) * cfg.round_to)
            escalations.append({"agent_id": rid, "district": district[rid], "risk_score": float(s.at[rid, "risk_score"]),
                                "unresolved_need": unresolved,
                                "replenishment_cost": logistics.replenishment_cost(district[rid], lat[rid], lon[rid],
                                                                                    unresolved, lcfg),
                                "reason": reason})

    legs_per_dest: dict[str, int] = {}
    for rec in recs:
        legs_per_dest[rec["destination_agent"]] = legs_per_dest.get(rec["destination_agent"], 0) + 1
    for rec in recs:
        did, rid = rec["source_agent"], rec["destination_agent"]
        r, d = s.loc[rid], s.loc[did]
        rec.update({
            "source_cash_before": round(float(d["cash_balance"]), 2), "source_cash_after": round(cash[did], 2),
            "source_protected_level": round(float(reserve[did]), 2),
            "donor_margin_after_plan": round(cash[did] - reserve[did], 2),
            "destination_cash_before": round(float(r["cash_balance"]), 2), "destination_cash_after": round(cash[rid], 2),
            "destination_requirement_p50": round(p50[rid], 2), "destination_requirement_p90": round(p90[rid], 2),
            "destination_target_cash": round(float(recipient_target(p50[rid], p90[rid], cfg)), 2),
            "legs_for_destination": legs_per_dest[rid],
        })
        if with_details:
            rec["destination_risk_before"] = _risk_for(float(r["cash_balance"]), r)
            rec["destination_risk_after"] = _risk_for(cash[rid], r)
            rec["source_risk_before"] = _risk_for(float(d["cash_balance"]), d)
            rec["source_risk_after"] = _risk_for(cash[did], d)
            eb = rec["expected_benefit"]
            rec["reason"] = (
                f"Selected because this transfer {eb['gate_reason']} for {rid} "
                f"({eb['risk_level_before']} {eb['risk_score_before']:.0f} → {eb['risk_level_after']} "
                f"{eb['risk_score_after']:.0f}; expected shortfall reduced by {risk.bdt(eb['shortfall_reduction_bdt'])}), "
                f"while donor {did} stays {rec['source_risk_after']['risk_level']} with {risk.bdt(rec['donor_margin_after_plan'])} "
                f"above its dynamic protected reserve of {risk.bdt(reserve[did])}; {rec['distance_km']:.1f} km, "
                f"simulated logistics cost proxy {risk.bdt(rec['logistics_cost']['total_estimated_cost_bdt'])}.")
    summary = {
        "policy": "v2",
        "n_recommendations": len(recs),
        "total_recommended_amount": float(sum(x["recommended_amount"] for x in recs)),
        "recipients_supported": len({x["destination_agent"] for x in recs}),
        "n_escalations": len(escalations),
        "escalated_amount": float(sum(x["unresolved_need"] for x in escalations)),
        "n_held_for_review": len(held),
        "n_gate_rejections": gate_rejections,
        "estimated_cost_bdt": float(sum(x["estimated_cost_bdt"] for x in recs)),
        **logistics_summary(recs, escalations, lcfg),
        "config": asdict(cfg),
    }
    return {"recommendations": recs, "escalations": escalations, "held_for_review": held, "summary": summary}
