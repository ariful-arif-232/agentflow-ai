"""Held-out business impact simulation.

Replays the held-out test period hour by hour for every agent, using the *same*
exogenous customer demand under three policies:

* ``status_quo``        — no proactive rebalancing (manual 08:00 drawer reset only);
* ``naive_rebalancing`` — the AgentFlow risk + rebalancing engine fed by naive seasonal forecasts;
* ``agentflow``         — the full AgentFlow loop with ML forecasts.

At each decision hour the engine sees only information available at that hour (current
simulated cash + forecasts built from past data). Approved transfers are assumed to
arrive one hour later (field logistics delay). Rebalancing is peer-to-peer, so total cash
in the network is identical across policies — any gain comes from *where* cash sits.

Synthetic held-out simulation — not a measured real-world upay result.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import config, data_gen, rebalance, risk

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
    "estimated_logistics_cost_bdt": "Sum of per-transfer cost estimates (fixed BDT 150 + BDT 25/km).",
}


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
                    demand_multiplier: float = 1.0) -> dict:
    """Simulate one policy. forecast_source in {"none", "ml", "naive"}."""
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
            plan = rebalance.recommend(snap, cfg, with_details=False)
            idx = {a: i for i, a in enumerate(agent_ids)}
            for rec in plan["recommendations"]:
                # Transfer leaves the donor and reaches the recipient at the start of the next hour.
                pending[idx[rec["source_agent"]]] -= rec["recommended_amount"]
                pending[idx[rec["destination_agent"]]] += rec["recommended_amount"]
                log.append({"t": t, "timestamp": hours[t], **rec})
    # donors cannot go negative: transfers are bounded by surplus measured at decision time,
    # but demand in the decision hour has already been served, so cash >= amount holds.
    return {"hours": hours, "agent_ids": agent_ids, "unmet": unmet, "cash_end": cash_end,
            "out_req": out_req, "log": log}


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


def run_impact(feats, agents, preds, hist_rate, anomaly_status=None, demand_multiplier: float = 1.0) -> dict:
    sims = {
        "status_quo": simulate_policy(feats, agents, None, hist_rate, forecast_source="none",
                                      demand_multiplier=demand_multiplier),
        "naive_rebalancing": simulate_policy(feats, agents, preds, hist_rate, anomaly_status, "naive",
                                             demand_multiplier=demand_multiplier),
        "agentflow": simulate_policy(feats, agents, preds, hist_rate, anomaly_status, "ml",
                                     demand_multiplier=demand_multiplier),
    }
    base = sims["status_quo"]["unmet"]
    policies = {k: summarize(v, base) for k, v in sims.items()}
    sq, af = policies["status_quo"], policies["agentflow"]

    def pct(a, b):
        return 100 * (a - b) / a if a else 0.0

    return {
        "label": "Synthetic held-out simulation",
        "period": {"start": str(sims["status_quo"]["hours"][0]), "end": str(sims["status_quo"]["hours"][-1]),
                   "hours": len(sims["status_quo"]["hours"]), "agents": len(agents)},
        "assumptions": {
            "decision_hours": list(DECISION_HOURS), "transfer_delay_hours": 1,
            "rebalancing": "peer-to-peer within district, <= 15 km, donor keeps >= 110% of its P90 requirement",
            "cash_neutral": True, "demand_multiplier": demand_multiplier,
            "anomalous_agents": "held for manual review (not auto-supported)",
        },
        "metric_definitions": METRIC_DEFINITIONS,
        "policies": policies,
        "agentflow_vs_status_quo": {
            "shortage_events_reduction_pct": pct(sq["shortage_events"], af["shortage_events"]),
            "unmet_demand_reduction_pct": pct(sq["unmet_cash_demand_bdt"], af["unmet_cash_demand_bdt"]),
            "unmet_demand_avoided_bdt": sq["unmet_cash_demand_bdt"] - af["unmet_cash_demand_bdt"],
            "service_availability_gain_pp": af["service_availability_pct"] - sq["service_availability_pct"],
        },
        "daily": daily_series(sims),
        "groups": group_breakdown(sims, agents),
    }
