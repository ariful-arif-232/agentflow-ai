"""Explainable, safety-constrained liquidity rebalancing recommendations.

Greedy constrained optimiser
----------------------------
1. Recipients: agents whose liquidity risk is HIGH/CRITICAL. Agents with an ANOMALOUS
   behavioural status are *held for manual review* instead of receiving a recommendation.
2. Recipient need = P90 forecast requirement - current cash (bring coverage to the P90 scenario).
3. Donors: LOW-risk, non-anomalous agents in the same district. A donor's *protected level*
   is max(110% of its own P90 requirement, BDT 5,000); only cash above that level
   (safe surplus) can ever be recommended.
4. Recipients are served in descending risk order; each takes from up to two nearest
   donors within 15 km (distance ~ operational cost), in BDT 500 steps, minimum BDT 2,000.
5. Remaining need is escalated to distributor replenishment.

Invariants (tested): amount <= donor safe surplus, no negative balances, donors never
pushed below their protected level, and the input snapshot is never mutated.
Recommendations are decision support only — nothing is executed without human approval,
and approval only runs a simulation.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

from . import risk

TRIGGER_LEVELS = ("HIGH", "CRITICAL")


@dataclass(frozen=True)
class RebalanceConfig:
    max_distance_km: float = 15.0
    donor_buffer_ratio: float = 1.10
    donor_min_floor: float = 5_000.0
    min_transfer: float = 2_000.0
    round_to: float = 500.0
    max_donors_per_recipient: int = 2
    cost_fixed_bdt: float = 150.0
    cost_per_km_bdt: float = 25.0


def haversine_km(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 6371.0 * 2 * np.arcsin(np.sqrt(a))


def protected_level(p90, cfg: RebalanceConfig = RebalanceConfig()):
    return np.maximum(cfg.donor_buffer_ratio * np.asarray(p90, float), cfg.donor_min_floor)


def _risk_for(cash, row) -> dict:
    r = risk.compute_risk([cash], [row["pred_net_requirement_6h"]], [row["pred_net_requirement_p90_6h"]],
                          [row["velocity_ratio_3h"]], [row["hist_shortage_rate"]]).iloc[0]
    return {"risk_score": float(r["risk_score"]), "risk_level": str(r["risk_level"]),
            "coverage_ratio": None if pd.isna(r["coverage_ratio"]) else float(r["coverage_ratio"])}


def recommend(snap: pd.DataFrame, cfg: RebalanceConfig = RebalanceConfig(),
              with_details: bool = True) -> dict:
    """Return {"recommendations": [...], "escalations": [...], "held_for_review": [...], "summary": {...}}."""
    s = snap.set_index("agent_id", drop=False)
    cash = s["cash_balance"].astype(float).to_dict()
    is_recipient = s["risk_level"].isin(TRIGGER_LEVELS)
    anomalous = s["anomaly_status"] == "ANOMALOUS"
    prot = pd.Series(protected_level(s["pred_net_requirement_p90_6h"], cfg), index=s.index)
    surplus = (s["cash_balance"] - prot).clip(lower=0)
    donor_ok = (s["risk_level"] == "LOW") & ~anomalous & (surplus >= cfg.min_transfer)
    remaining = surplus.where(donor_ok, 0.0).to_dict()

    recs, escalations, held = [], [], []
    recipients = s[is_recipient].sort_values(["risk_score", "expected_shortfall"], ascending=False)
    for rid, r in recipients.iterrows():
        need = max(float(r["pred_net_requirement_p90_6h"]) - cash[rid], 0.0)
        if need < cfg.min_transfer:
            continue
        if anomalous[rid]:
            held.append({"agent_id": rid, "risk_score": float(r["risk_score"]), "need": round(need, 0),
                         "reason": "Behavioural anomaly detected — manual review required before any liquidity support."})
            continue
        cands = s[(s["district"] == r["district"]) & (s.index != rid)]
        cands = cands[[remaining.get(a, 0.0) >= cfg.min_transfer for a in cands.index]]
        if len(cands):
            dist = haversine_km(r["synthetic_latitude"], r["synthetic_longitude"],
                                cands["synthetic_latitude"].to_numpy(), cands["synthetic_longitude"].to_numpy())
            cands = cands.assign(distance_km=dist)
            cands = cands[cands["distance_km"] <= cfg.max_distance_km]
            cands = cands.assign(avail=[remaining[a] for a in cands.index]).sort_values(
                ["distance_km", "avail"], ascending=[True, False])
        used = 0
        for did, d in cands.iterrows():
            if used >= cfg.max_donors_per_recipient or need < cfg.min_transfer:
                break
            amount = np.floor(min(need, remaining[did]) / cfg.round_to) * cfg.round_to
            if amount < cfg.min_transfer:
                continue
            cash[did] -= amount
            cash[rid] += amount
            remaining[did] -= amount
            need -= amount
            used += 1
            recs.append({
                "id": f"RB-{len(recs) + 1:03d}",
                "source_agent": did, "destination_agent": rid,
                "recommended_amount": float(amount),
                "district": r["district"],
                "distance_km": round(float(d["distance_km"]), 2),
                "estimated_cost_bdt": round(cfg.cost_fixed_bdt + cfg.cost_per_km_bdt * float(d["distance_km"]), 0),
                "donor_rank": used,
            })
        if need >= cfg.min_transfer:
            escalations.append({"agent_id": rid, "district": r["district"], "risk_score": float(r["risk_score"]),
                                "unresolved_need": float(np.ceil(need / cfg.round_to) * cfg.round_to),
                                "reason": "No eligible peer surplus within range — escalate to distributor replenishment."})
    # Plan-level before/after: "before" = current state, "after" = state once every
    # recommendation in this plan is applied (an agent may appear in several legs).
    legs_per_dest: dict[str, int] = {}
    for rec in recs:
        legs_per_dest[rec["destination_agent"]] = legs_per_dest.get(rec["destination_agent"], 0) + 1
    for rec in recs:
        did, rid = rec["source_agent"], rec["destination_agent"]
        r, d = s.loc[rid], s.loc[did]
        rec.update({
            "source_cash_before": round(float(d["cash_balance"]), 2), "source_cash_after": round(cash[did], 2),
            "source_protected_level": round(float(prot[did]), 2),
            "destination_cash_before": round(float(r["cash_balance"]), 2), "destination_cash_after": round(cash[rid], 2),
            "destination_requirement_p50": round(float(r["pred_net_requirement_6h"]), 2),
            "destination_requirement_p90": round(float(r["pred_net_requirement_p90_6h"]), 2),
            "legs_for_destination": legs_per_dest[rid],
        })
        if with_details:
            rec["destination_risk_before"] = _risk_for(float(r["cash_balance"]), r)
            rec["destination_risk_after"] = _risk_for(cash[rid], r)
            rec["source_risk_before"] = _risk_for(float(d["cash_balance"]), d)
            rec["source_risk_after"] = _risk_for(cash[did], d)
            rank = "nearest" if rec["donor_rank"] == 1 else "next-nearest"
            rec["reason"] = (
                f"{rid} is {r['risk_level']} risk (score {r['risk_score']:.0f}): forecast 6-hour requirement "
                f"{risk.bdt(r['pred_net_requirement_6h'])} (P90 {risk.bdt(r['pred_net_requirement_p90_6h'])}) against "
                f"{risk.bdt(r['cash_balance'])} cash. {did} is the {rank} eligible surplus agent in {r['district']} "
                f"({rec['distance_km']:.1f} km), LOW risk, and keeps {risk.bdt(cash[did])} after the plan — above its "
                f"protected level of {risk.bdt(prot[did])} (110% of its own P90 requirement).")
    summary = {
        "n_recommendations": len(recs),
        "total_recommended_amount": float(sum(x["recommended_amount"] for x in recs)),
        "recipients_supported": len({x["destination_agent"] for x in recs}),
        "n_escalations": len(escalations),
        "escalated_amount": float(sum(x["unresolved_need"] for x in escalations)),
        "n_held_for_review": len(held),
        "estimated_cost_bdt": float(sum(x["estimated_cost_bdt"] for x in recs)),
        "config": asdict(cfg),
    }
    return {"recommendations": recs, "escalations": escalations, "held_for_review": held, "summary": summary}


def transfers_to_cash_delta(recs: list[dict]) -> dict[str, float]:
    delta: dict[str, float] = {}
    for r in recs:
        delta[r["source_agent"]] = delta.get(r["source_agent"], 0.0) - r["recommended_amount"]
        delta[r["destination_agent"]] = delta.get(r["destination_agent"], 0.0) + r["recommended_amount"]
    return delta
