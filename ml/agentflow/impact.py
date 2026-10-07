"""Held-out business impact simulation.

Replays the held-out test period hour by hour for every agent, using the *same*
exogenous customer demand under four policies:

* ``status_quo``        — no proactive rebalancing (manual 08:00 drawer reset only);
* ``naive_rebalancing`` — the AgentFlow risk + rebalancing engine fed by naive seasonal forecasts;
* ``agentflow``         — the full AgentFlow loop with ML forecasts and rebalancing policy V1;
* ``agentflow_v2``      — the same loop with rebalancing policy V2 (cost-, uncertainty- and
  safety-aware; parameters selected on training-period policy-validation folds only).

At each decision hour the engine sees only information available at that hour (current
simulated cash + forecasts built from past data). Approved transfers are assumed to
arrive one hour later (field logistics delay). Rebalancing is peer-to-peer, so total cash
in the network is identical across policies — any gain comes from *where* cash sits.

Phase-2 logistics metrics (``phase2_logistics`` block) re-cost every simulated transfer and every
distributor escalation with the synthetic operational cost proxy in ``logistics.py``, and keep the
held-out result of the *experimental* V2 ranked by that richer cost (not adopted). The Phase-1
``policies`` block is unchanged and uses the serving Phase-1 V2 ranking (BDT 150 + BDT 25/km).

Synthetic held-out simulation — not a measured real-world upay result.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from dataclasses import replace

from . import config, data_gen, logistics, rebalance, rebalance_v2, risk

DECISION_HOURS = (9, 11, 13, 15, 17, 19)
OPERATING_HOURS = range(8, 22)

METRIC_DEFINITIONS = {
    "shortage_events": "Agent-hours in which at least one requested cash-out could not be served.",
    "unmet_cash_demand_bdt": "Total requested cash-out (BDT) not served because the agent lacked cash.",
    "agents_with_shortage": "Number of agents with at least one shortage event in the period.",
    "service_availability_pct": ("Share of operating agent-hours (08:00-21:59) with customer cash-out demand "
                                 "in which all requested cash-out was served."),
    "demand_fill_rate_pct": "Served cash-out / requested cash-out over the period.",
    "interventions": "Number of simulated peer rebalancing transfers (each is human-approved in production).",
    "total_rebalanced_bdt": "Total cash moved between agents by simulated transfers.",
    "unnecessary_interventions_pct": ("Share of transfers whose recipient would NOT have had any shortage in the "
                                      "following 6 hours under the status-quo policy (false alerts)."),
    "donor_shortage_events_after_transfer": ("Shortage events at donor agents within 6 hours after they gave cash "
                                             "(safety check; should be ~0)."),
    "estimated_logistics_cost_bdt": "Sum of per-transfer cost estimates (Phase-1 estimate: fixed BDT 150 + BDT 25/km).",
    "escalated_need_bdt": ("Sum, over all decision points, of at-risk need that peer rebalancing could not cover "
                           "(handed to distributor replenishment; the same agent can be counted at several decisions)."),
    "unmet_avoided_per_transfer_bdt": "Unmet cash demand avoided vs. status quo divided by the number of transfers.",
    "unmet_avoided_per_1000_cost_bdt": "Unmet cash demand avoided vs. status quo per BDT 1,000 of estimated logistics cost.",
    "shortage_events_avoided_per_100_transfers": "Shortage events avoided vs. status quo per 100 transfers.",
}


PHASE2_METRIC_DEFINITIONS = {
    "peer_transfer_logistics_cost_bdt": ("Sum over simulated peer transfers of the synthetic operational cost proxy "
                                         "(handling + round-trip distance + field-officer time + cash-in-transit)."),
    "average_cost_per_transfer_bdt": "Peer-transfer logistics cost proxy divided by the number of transfers.",
    "peer_cost_components_bdt": "The peer-transfer cost proxy split into handling, distance, time and cash-in-transit.",
    "peer_cash_in_transit_cost_bdt": "Cash-in-transit exposure component of the peer-transfer cost proxy (bps of amount moved).",
    "distributor_escalation_cost_proxy_bdt": ("Upper-bound proxy: one distributor trip from the synthetic district hub "
                                              "for every escalation at every decision point (the same agent can be "
                                              "escalated at several decision points). Escalations are not executed in "
                                              "the simulation, so they avoid no unmet demand here."),
    "total_operational_logistics_cost_proxy_bdt": "Peer-transfer cost proxy + distributor escalation cost proxy.",
    "unmet_avoided_per_1000_peer_logistics_cost_bdt": ("Unmet cash demand avoided vs. status quo per BDT 1,000 of the "
                                                       "peer-transfer logistics cost proxy."),
    "unmet_avoided_per_1000_total_logistics_cost_bdt": ("Unmet cash demand avoided vs. status quo per BDT 1,000 of the "
                                                        "total operational logistics cost proxy (conservative: includes "
                                                        "escalation trips whose benefit is not simulated)."),
}
COST_PARTS = ("base_handling_bdt", "distance_cost_bdt", "time_cost_bdt", "cash_in_transit_cost_bdt")


def _matrices(feats: pd.DataFrame, agent_ids: list[str], hours: pd.DatetimeIndex, cols: list[str]):
    sub = feats[feats["timestamp"].isin(hours)]
    out = {}
    for c in cols:
        m = sub.pivot(index="timestamp", columns="agent_id", values=c).reindex(index=hours, columns=agent_ids)
        out[c] = m.to_numpy(dtype=float)
    return out, sub


def simulate_policy(feats: pd.DataFrame, agents: pd.DataFrame, preds: pd.DataFrame | None,
                    hist_rate: pd.Series, anomaly_status: pd.DataFrame | None = None,
                    forecast_source: str = "ml", start: pd.Timestamp = config.TEST_START,
                    end: pd.Timestamp | None = None, cfg: rebalance.RebalanceConfig = rebalance.RebalanceConfig(),
                    demand_multiplier: float = 1.0, policy: str = "v1",
                    policy_cfg: rebalance_v2.RebalanceV2Config | None = None) -> dict:
    """Simulate one policy. forecast_source in {"none", "ml", "naive"}; policy in {"v1", "v2"}."""
    if policy not in ("v1", "v2"):
        raise ValueError("policy must be 'v1' or 'v2'")
    if policy == "v2" and policy_cfg is None:
        policy_cfg = rebalance_v2.selected_config()
    agent_ids = list(agents["agent_id"])
    end = end or feats["timestamp"].max()
    hours = pd.date_range(start, end, freq="h")
    mats, sub = _matrices(feats, agent_ids, hours, ["cash_out_amount", "cash_in_amount", "velocity_ratio_3h"])
    out_req = mats["cash_out_amount"] * demand_multiplier
    cash_in = mats["cash_in_amount"]
    hod = hours.hour.to_numpy()
    prev = feats[feats["timestamp"] == start - pd.Timedelta(hours=1)].set_index("agent_id")["cash_balance"]
    cash = prev.reindex(agent_ids).to_numpy(dtype=float)
    target = agents.set_index("agent_id")["target_cash_level"].reindex(agent_ids).to_numpy(dtype=float)

    if forecast_source == "ml":
        p = preds.reindex(sub.index).assign(timestamp=sub["timestamp"], agent_id=sub["agent_id"])
        p50 = p.pivot(index="timestamp", columns="agent_id", values="pred_net_requirement_6h")
        p90 = p.pivot(index="timestamp", columns="agent_id", values="pred_net_requirement_p90_6h")
    elif forecast_source == "naive":
        p50 = sub.pivot(index="timestamp", columns="agent_id", values="net_req_same_window_avg7")
        p90 = sub.pivot(index="timestamp", columns="agent_id", values="net_req_same_window_max7")
    if forecast_source != "none":
        p50 = p50.reindex(index=hours, columns=agent_ids).to_numpy(float) * demand_multiplier
        p90 = p90.reindex(index=hours, columns=agent_ids).to_numpy(float) * demand_multiplier
        static = agents.set_index("agent_id").reindex(agent_ids)
        hist = hist_rate.reindex(agent_ids).fillna(0).to_numpy()
        if anomaly_status is not None:
            anom = anomaly_status.reindex(index=hours, columns=agent_ids).fillna("NORMAL").to_numpy()

    n_h, n_a = out_req.shape
    unmet = np.zeros((n_h, n_a))
    cash_end = np.zeros((n_h, n_a))
    pending = np.zeros(n_a)
    log = []
    escalated_need = 0.0
    escalation_cost = {"events": 0, "unavailable": 0, "cost_bdt": 0.0, "cash_in_transit_bdt": 0.0}
    escalation_log = []  # per escalation, for the Phase-2 business-impact layer (not written to impact.json)
    for t in range(n_h):
        if hod[t] == data_gen.OPENING_HOUR:
            cash = target.copy()
        cash = cash + pending
        pending = np.zeros(n_a)
        available = cash + cash_in[t]
        served = np.minimum(out_req[t], available)
        unmet[t] = out_req[t] - served
        cash = available - served
        cash_end[t] = cash
        if forecast_source != "none" and hod[t] in DECISION_HOURS and t + 1 < n_h:
            r = risk.compute_risk(cash, np.nan_to_num(p50[t]), np.nan_to_num(p90[t]),
                                  mats["velocity_ratio_3h"][t], hist)
            snap = pd.DataFrame({
                "agent_id": agent_ids, "district": static["district"].to_numpy(),
                "synthetic_latitude": static["synthetic_latitude"].to_numpy(),
                "synthetic_longitude": static["synthetic_longitude"].to_numpy(),
                "cash_balance": cash, "pred_net_requirement_6h": np.nan_to_num(p50[t]),
                "pred_net_requirement_p90_6h": np.maximum(np.nan_to_num(p90[t]), np.nan_to_num(p50[t])),
                "velocity_ratio_3h": mats["velocity_ratio_3h"][t], "hist_shortage_rate": hist,
                "anomaly_status": anom[t] if anomaly_status is not None else "NORMAL",
            }).join(r[["risk_score", "risk_level", "expected_shortfall"]])
            if policy == "v1":
                plan = rebalance.recommend(snap, cfg, with_details=False)
            else:
                plan = rebalance_v2.recommend_v2(snap, policy_cfg, with_details=False)
            escalated_need += plan["summary"]["escalated_amount"]
            lg = plan["summary"]["logistics"]
            escalation_cost["events"] += lg["escalations_costed"]
            escalation_cost["unavailable"] += lg["escalations_cost_unavailable"]
            escalation_cost["cost_bdt"] += lg["escalation_replenishment_cost_bdt"]
            escalation_cost["cash_in_transit_bdt"] += lg["escalation_cash_in_transit_cost_bdt"]
            for e in plan["escalations"]:
                rc = e.get("replenishment_cost", {})
                escalation_log.append({"t": t, "agent_id": e["agent_id"], "unresolved_need": e["unresolved_need"],
                                       "cost_bdt": rc.get("total_estimated_cost_bdt") if rc.get("available") else None})
            idx = {a: i for i, a in enumerate(agent_ids)}
            for rec in plan["recommendations"]:
                # Transfer leaves the donor and reaches the recipient at the start of the next hour.
                pending[idx[rec["source_agent"]]] -= rec["recommended_amount"]
                pending[idx[rec["destination_agent"]]] += rec["recommended_amount"]
                log.append({"t": t, "timestamp": hours[t], **rec})
    # donors cannot go negative: transfers are bounded by surplus measured at decision time,
    # but demand in the decision hour has already been served, so cash >= amount holds.
    return {"hours": hours, "agent_ids": agent_ids, "unmet": unmet, "cash_end": cash_end,
            "out_req": out_req, "log": log, "escalated_need_bdt": escalated_need, "escalation_cost": escalation_cost,
            "escalation_log": escalation_log,
            "policy": policy if forecast_source != "none" else None}


def summarize(sim: dict, baseline_unmet: np.ndarray | None = None) -> dict:
    hours, unmet, out_req = sim["hours"], sim["unmet"], sim["out_req"]
    op = np.isin(hours.hour, list(OPERATING_HOURS))
    short = unmet > 0.5
    demand_hours = (out_req > 0) & op[:, None]
    res = {
        "shortage_events": int(short.sum()),
        "unmet_cash_demand_bdt": float(unmet.sum()),
        "agents_with_shortage": int(short.any(axis=0).sum()),
        "service_availability_pct": float(100 * (1 - (short & demand_hours).sum() / max(demand_hours.sum(), 1))),
        "demand_fill_rate_pct": float(100 * (1 - unmet.sum() / max(out_req.sum(), 1))),
        "interventions": len(sim["log"]),
        "total_rebalanced_bdt": float(sum(x["recommended_amount"] for x in sim["log"])),
        "estimated_logistics_cost_bdt": float(sum(x["estimated_cost_bdt"] for x in sim["log"])),
    }
    if sim.get("policy"):
        res["escalated_need_bdt"] = float(sim.get("escalated_need_bdt", 0.0))
    if sim["log"]:
        idx = {a: i for i, a in enumerate(sim["agent_ids"])}
        donor_short = 0
        unnecessary = 0
        for x in sim["log"]:
            t = x["t"]
            w = slice(t + 1, min(t + 7, len(hours)))
            donor_short += int(short[w, idx[x["source_agent"]]].sum())
            if baseline_unmet is not None and baseline_unmet[w, idx[x["destination_agent"]]].sum() <= 0.5:
                unnecessary += 1
        res["donor_shortage_events_after_transfer"] = donor_short
        if baseline_unmet is not None:
            res["unnecessary_interventions_pct"] = 100 * unnecessary / len(sim["log"])
    return res


def logistics_metrics(sim: dict, sq_unmet_bdt: float) -> dict:
    """Phase-2 derived cost metrics for one simulated policy (synthetic operational cost proxy)."""
    log = sim["log"]
    parts = {k: round(sum(x["logistics_cost"][k] for x in log), 2) for k in COST_PARTS}
    peer = round(sum(parts.values()), 2)
    esc = sim.get("escalation_cost", {"events": 0, "unavailable": 0, "cost_bdt": 0.0, "cash_in_transit_bdt": 0.0})
    total = round(peer + esc["cost_bdt"], 2)
    avoided = sq_unmet_bdt - float(sim["unmet"].sum())
    return {
        "interventions": len(log),
        "peer_transfer_logistics_cost_bdt": peer,
        "average_cost_per_transfer_bdt": round(peer / len(log), 2) if log else None,
        "peer_cost_components_bdt": parts,
        "peer_cash_in_transit_cost_bdt": parts["cash_in_transit_cost_bdt"],
        "distributor_escalation_cost_proxy_bdt": round(esc["cost_bdt"], 2),
        "distributor_escalation_cash_in_transit_bdt": round(esc["cash_in_transit_bdt"], 2),
        "distributor_escalation_events_costed": int(esc["events"]),
        "distributor_escalation_events_unavailable": int(esc["unavailable"]),
        "total_operational_logistics_cost_proxy_bdt": total,
        "unmet_avoided_bdt": avoided,
        "unmet_avoided_per_1000_peer_logistics_cost_bdt": 1000 * avoided / peer if peer else None,
        "unmet_avoided_per_1000_total_logistics_cost_bdt": 1000 * avoided / total if total else None,
    }


EXPERIMENT_STATUS = ("EXPERIMENTAL — not adopted. Ranking V2 donors by the logistics-cost proxy did not improve "
                     "held-out outcomes (more shortage events, more unmet demand, one more donor shortage), so the "
                     "serving default keeps the Phase-1 ranking. The proxy is still used to cost every transfer.")


def phase2_logistics(sims: dict, policies: dict, v2_logistics_sim: dict, v2_cfg) -> dict:
    """Phase-2 block: the Phase-1 simulations re-costed with the proxy, plus the ranking experiment.

    ``policies.agentflow_v2`` is the serving V2 (Phase-1 ranking); the logistics-ranked V2 is kept as
    ``policies.agentflow_v2_logistics_ranking_experiment`` and is never mixed into the serving figures.
    """
    from . import policy_selection

    base = sims["status_quo"]["unmet"]
    sq = policies["status_quo"]
    sq_unmet = sq["unmet_cash_demand_bdt"]
    v2l = summarize(v2_logistics_sim, base)
    v2l.update(policy_selection.efficiency(v2l, sq))
    out_pol = {
        "naive_rebalancing": logistics_metrics(sims["naive_rebalancing"], sq_unmet),
        "agentflow": logistics_metrics(sims["agentflow"], sq_unmet),
        "agentflow_v2": logistics_metrics(sims["agentflow_v2"], sq_unmet),
        "agentflow_v2_logistics_ranking_experiment": {**v2l, **logistics_metrics(v2_logistics_sim, sq_unmet)},
    }
    core = ("shortage_events", "unmet_cash_demand_bdt", "agents_with_shortage", "service_availability_pct",
            "demand_fill_rate_pct", "interventions", "total_rebalanced_bdt", "unnecessary_interventions_pct",
            "donor_shortage_events_after_transfer", "escalated_need_bdt")
    old, new = policies["agentflow_v2"], v2l
    legs = lambda sim: {(x["t"], x["source_agent"], x["destination_agent"], x["recommended_amount"]) for x in sim["log"]}
    changed = len(legs(sims["agentflow_v2"]) ^ legs(v2_logistics_sim)) // 2

    def pct(a, b):
        return 100 * (a - b) / a if a else 0.0

    v1l = {**policies["agentflow"], "unmet_avoided_per_1000_cost_bdt": out_pol["agentflow"]["unmet_avoided_per_1000_peer_logistics_cost_bdt"]}
    v2d = {**v2l, "unmet_avoided_per_1000_cost_bdt":
           out_pol["agentflow_v2_logistics_ranking_experiment"]["unmet_avoided_per_1000_peer_logistics_cost_bdt"]}
    return {
        "label": "Phase-2 logistics metrics — synthetic operational cost proxy, not upay measured cost",
        "version": "phase2-logistics-2",
        "changes_from_phase2_logistics_1": (
            "Keys renamed so the serving default is unambiguous: policies.agentflow_v2_phase1_ranking -> "
            "policies.agentflow_v2 (serving, Phase-1 ranking); policies.agentflow_v2 (logistics ranking) -> "
            "policies.agentflow_v2_logistics_ranking_experiment. All values are unchanged."),
        "assumptions": logistics.describe(),
        "metric_definitions": PHASE2_METRIC_DEFINITIONS,
        "serving_v2_ranking_cost_model": rebalance_v2.SERVING_RANKING_COST_MODEL,
        "experiment_ranking_cost_model": v2_cfg.ranking_cost_model,
        "experiment_status": EXPERIMENT_STATUS,
        "v2_parameters_note": ("V2 tunable parameters are unchanged: selected on Phase-1 training-period validation "
                               "folds with the Phase-1 cost. The experiment changed only the cost term of the ranking."),
        "not_costed": "The daily 08:00 drawer reset is common to every policy and is not costed.",
        "policies": out_pol,
        "v2_ranking_change": {
            "phase1_ranking": {k: old.get(k) for k in core},
            "logistics_proxy_ranking": {k: new.get(k) for k in core},
            "transfer_legs_changed": changed,
            "v2_vs_status_quo": {
                "phase1_ranking": {"shortage_events_reduction_pct": pct(sq["shortage_events"], old["shortage_events"]),
                                   "unmet_demand_reduction_pct": pct(sq_unmet, old["unmet_cash_demand_bdt"])},
                "logistics_proxy_ranking": {"shortage_events_reduction_pct": pct(sq["shortage_events"], new["shortage_events"]),
                                            "unmet_demand_reduction_pct": pct(sq_unmet, new["unmet_cash_demand_bdt"])},
            },
        },
        "deployment_rule_recheck": {
            **policy_selection.deployment_decision(v1l, v2d),
            "note": ("Same pre-registered rule, re-applied to the logistics-ranked V2 experiment, with cost efficiency "
                     "measured by the peer-transfer logistics cost proxy for both V1 and V2. Passing this rule does not "
                     "make the experiment better than the Phase-1-ranked V2, which remains the serving default."),
        },
    }


def daily_series(sims: dict[str, dict]) -> list[dict]:
    rows = []
    any_sim = next(iter(sims.values()))
    days = any_sim["hours"].normalize()
    for day in sorted(set(days)):
        m = days == day
        row = {"date": str(day.date())}
        for name, s in sims.items():
            row[f"{name}_unmet_bdt"] = float(s["unmet"][m].sum())
            row[f"{name}_shortage_events"] = int((s["unmet"][m] > 0.5).sum())
        rows.append(row)
    return rows


def group_breakdown(sims: dict[str, dict], agents: pd.DataFrame) -> dict:
    a = agents.set_index("agent_id").reindex(next(iter(sims.values()))["agent_ids"])
    out = {}
    for gcol in ("location_cluster", "agent_volume_segment"):
        out[gcol] = {}
        for g in sorted(a[gcol].unique()):
            m = (a[gcol] == g).to_numpy()
            out[gcol][g] = {name: {"unmet_cash_demand_bdt": float(s["unmet"][:, m].sum()),
                                   "shortage_events": int((s["unmet"][:, m] > 0.5).sum())}
                            for name, s in sims.items()}
    return out


def run_impact(feats, agents, preds, hist_rate, anomaly_status=None, demand_multiplier: float = 1.0,
               v2_cfg: rebalance_v2.RebalanceV2Config | None = None) -> dict:
    from . import policy_selection

    v2_cfg = v2_cfg or rebalance_v2.selected_config()
    v2_phase1_cfg = replace(v2_cfg, ranking_cost_model="phase1_simple")  # serving default = Phase-1 evidence
    v2_experiment_cfg = replace(v2_cfg, ranking_cost_model=rebalance_v2.EXPERIMENT_RANKING_COST_MODEL)  # explicit
    sims = {
        "status_quo": simulate_policy(feats, agents, None, hist_rate, forecast_source="none",
                                      demand_multiplier=demand_multiplier),
        "naive_rebalancing": simulate_policy(feats, agents, preds, hist_rate, anomaly_status, "naive",
                                             demand_multiplier=demand_multiplier),
        "agentflow": simulate_policy(feats, agents, preds, hist_rate, anomaly_status, "ml",
                                     demand_multiplier=demand_multiplier),
        "agentflow_v2": simulate_policy(feats, agents, preds, hist_rate, anomaly_status, "ml",
                                        demand_multiplier=demand_multiplier, policy="v2", policy_cfg=v2_phase1_cfg),
    }
    v2_logistics_sim = simulate_policy(feats, agents, preds, hist_rate, anomaly_status, "ml",
                                       demand_multiplier=demand_multiplier, policy="v2", policy_cfg=v2_experiment_cfg)
    base = sims["status_quo"]["unmet"]
    policies = {k: summarize(v, base) for k, v in sims.items()}
    sq, af, af2 = policies["status_quo"], policies["agentflow"], policies["agentflow_v2"]
    for k in ("naive_rebalancing", "agentflow", "agentflow_v2"):
        policies[k].update(policy_selection.efficiency(policies[k], sq))

    def pct(a, b):
        return 100 * (a - b) / a if a else 0.0

    def vs_sq(m):
        return {
            "shortage_events_reduction_pct": pct(sq["shortage_events"], m["shortage_events"]),
            "unmet_demand_reduction_pct": pct(sq["unmet_cash_demand_bdt"], m["unmet_cash_demand_bdt"]),
            "unmet_demand_avoided_bdt": sq["unmet_cash_demand_bdt"] - m["unmet_cash_demand_bdt"],
            "service_availability_gain_pp": m["service_availability_pct"] - sq["service_availability_pct"],
        }

    return {
        "label": "Synthetic held-out simulation",
        "period": {"start": str(sims["status_quo"]["hours"][0]), "end": str(sims["status_quo"]["hours"][-1]),
                   "hours": len(sims["status_quo"]["hours"]), "agents": len(agents)},
        "assumptions": {
            "decision_hours": list(DECISION_HOURS), "transfer_delay_hours": 1,
            "rebalancing": "peer-to-peer within district, <= 15 km, donor keeps >= 110% of its P90 requirement",
            "rebalancing_v2": ("V1 constraints plus dynamic donor reserve, recipient target P50+λ(P90-P50), "
                               "minimum-benefit gate and benefit-cost-safety donor ranking"),
            "v2_config": {k: getattr(v2_cfg, k) for k in rebalance_v2.RebalanceV2Config.tunable_fields()},
            "v2_ranking_cost_model_in_this_block": "phase1_simple (BDT 150 + BDT 25/km); see phase2_logistics",
            "v2_parameters_selected_on": "training-period policy-validation folds (see policy_selection.json)",
            "cash_neutral": True, "demand_multiplier": demand_multiplier,
            "anomalous_agents": "held for manual review (not auto-supported)",
        },
        "metric_definitions": METRIC_DEFINITIONS,
        "policies": policies,
        "agentflow_vs_status_quo": vs_sq(af),
        "agentflow_v2_vs_status_quo": vs_sq(af2),
        "deployment_decision": policy_selection.deployment_decision(af, af2),
        "daily": daily_series(sims),
        "groups": group_breakdown(sims, agents),
        "phase2_logistics": phase2_logistics(sims, policies, v2_logistics_sim, v2_experiment_cfg),
    }
