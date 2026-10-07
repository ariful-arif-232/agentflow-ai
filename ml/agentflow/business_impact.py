"""Phase-2 business-impact layer: simulation metrics translated into business KPIs.

Synthetic simulated estimate — not measured upay performance. This layer is additive and versioned
separately (``business_impact.json``). It re-runs the held-out policies of ``impact.py`` and never
changes the Phase-1 evidence (``impact.json`` → ``policies``) or the Phase-2 logistics evidence
(``impact.json`` → ``phase2_logistics``).

What is measured directly in the synthetic simulation
-----------------------------------------------------
* requested, served and unmet cash-out **value** (BDT), fill rate and shortage agent-hours;
* requested cash-out **transaction counts** (the dataset's ``cash_out_count``);
* peer transfers, escalation events and the Phase-2 logistics-cost proxy of each.

What is estimated, and how
--------------------------
The simulator works in BDT: a shortage removes value, not individual transactions, and the dataset
holds no transaction-level failures. Failed cash-out transactions are therefore an **estimate**,
counted as transaction-equivalents::

    estimated_failed_transactions = Σ_agent-hours  unmet_bdt ÷ average_cash_out_ticket_bdt

* Method A (headline): the ticket is that agent-hour's own synthetic average
  (``cash_out_amount ÷ cash_out_count``); if the hour has no counted transaction, the agent's
  location-cluster ticket from the generator is used.
* Method B (cross-check): the location-cluster ticket for every agent-hour.

Protected transactions = estimated failed (status quo) − estimated failed (policy).

Illustrative economics
----------------------
Only one financial rate is needed and it is **not in the dataset**: the agent commission on served
cash-out value, an explicit configurable assumption (``agent_commission_bps``). The default is a round
illustrative number, not the rate of upay or any other provider::

    illustrative_commission_protected = cash_out_value_protected × bps ÷ 10,000
    net_illustrative_value            = illustrative_commission_protected − peer_logistics_cost
    benefit_cost_ratio                = illustrative_commission_protected ÷ peer_logistics_cost
    break_even_commission_bps         = peer_logistics_cost ÷ cash_out_value_protected × 10,000

No customer-retention, lifetime-value or provider-revenue assumption is used, so no ROI is claimed.
Distributor profitability is not invented: without a supplied fee the layer reports distributor
workload, the logistics-cost proxy and the break-even fee per trip needed to cover it.
"""
from __future__ import annotations

import math
import os
from dataclasses import asdict, dataclass, fields, replace

import numpy as np
import pandas as pd

from . import config, data_gen, impact, logistics, rebalance_v2

VERSION = "phase2-business-2"
VERSION_NOTE = ("phase2-business-2: 'agentflow_v2' is the serving V2 (proven Phase-1 ranking), costed with the "
                "Phase-2 logistics proxy. The logistics-ranked V2 is kept separately as "
                "'agentflow_v2_logistics_ranking_experiment' and is never combined with the serving figures.")
LABEL = "Synthetic simulated estimate — not measured upay performance."
ENV_PREFIX = "AGENTFLOW_BUSINESS_"
NOT_ROI = ("No ROI is reported: a return on investment would need customer-retention, lifetime-value or "
           "provider-revenue assumptions that this synthetic prototype does not have.")
POLICY_LABELS = {
    "status_quo": "Without AgentFlow (status quo)",
    "agentflow_v1": "AgentFlow V1",
    "agentflow_v2": "AgentFlow V2 (serving default: Phase-1 ranking; costs from the Phase-2 proxy)",
    "agentflow_v2_logistics_ranking_experiment": "EXPERIMENT (not adopted): V2 ranked by the logistics-cost proxy",
}


@dataclass(frozen=True)
class BusinessAssumptions:
    """Illustrative, configurable. Override with AGENTFLOW_BUSINESS_<FIELD> environment variables."""
    agent_commission_bps: float = 50.0               # round illustrative number, not any provider's rate
    distributor_fee_per_trip_bdt: float | None = None  # optional; when absent only break-even is reported
    sensitivity_commission_bps: tuple[float, ...] = (25.0, 50.0, 100.0, 200.0)
    sensitivity_cost_multipliers: tuple[float, ...] = (0.5, 1.0, 1.5)

    def __post_init__(self) -> None:
        def ok(v, hi=math.inf):
            return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) and 0 <= v <= hi
        if not ok(self.agent_commission_bps, 10_000):
            raise ValueError("agent_commission_bps must be a number between 0 and 10,000")
        if self.distributor_fee_per_trip_bdt is not None and not ok(self.distributor_fee_per_trip_bdt):
            raise ValueError("distributor_fee_per_trip_bdt must be a finite number >= 0 (or unset)")
        if not self.sensitivity_commission_bps or not all(ok(v, 10_000) for v in self.sensitivity_commission_bps):
            raise ValueError("sensitivity_commission_bps must be non-empty, each between 0 and 10,000")
        if not self.sensitivity_cost_multipliers or not all(ok(v) and v > 0 for v in self.sensitivity_cost_multipliers):
            raise ValueError("sensitivity_cost_multipliers must be non-empty and > 0")


def assumptions_from_env(env: dict | None = None, base: BusinessAssumptions | None = None) -> BusinessAssumptions:
    """AGENTFLOW_BUSINESS_AGENT_COMMISSION_BPS and AGENTFLOW_BUSINESS_DISTRIBUTOR_FEE_PER_TRIP_BDT (numbers)."""
    env = os.environ if env is None else env
    base = base or BusinessAssumptions()
    over = {}
    for name in ("agent_commission_bps", "distributor_fee_per_trip_bdt"):
        raw = env.get(ENV_PREFIX + name.upper())
        if raw is not None and str(raw).strip() != "":
            try:
                over[name] = float(raw)
            except ValueError as exc:
                raise ValueError(f"{ENV_PREFIX}{name.upper()} must be a number") from exc
    return replace(base, **over)


def _div(a: float, b: float) -> float | None:
    return float(a / b) if b else None


# ------------------------------------------------------------------ transaction estimates
def ticket_matrix(out_amount: np.ndarray, out_count: np.ndarray, cluster_ticket: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Average cash-out ticket per agent-hour (Method A) and the mask of cells that used the fallback."""
    out_amount = np.asarray(out_amount, float)
    out_count = np.asarray(out_count, float)
    fallback = np.broadcast_to(np.asarray(cluster_ticket, float), out_amount.shape)
    if (fallback <= 0).any():
        raise ValueError("cluster tickets must be > 0")
    use_fallback = ~(out_count > 0)
    with np.errstate(divide="ignore", invalid="ignore"):
        own = np.where(out_count > 0, out_amount / np.where(out_count > 0, out_count, 1.0), 0.0)
    ticket = np.where(use_fallback | (own <= 0), fallback, own)
    return ticket, use_fallback


def estimated_failed_transactions(unmet: np.ndarray, ticket: np.ndarray) -> float:
    unmet = np.clip(np.asarray(unmet, float), 0.0, None)
    return float((unmet / np.asarray(ticket, float)).sum())


# ------------------------------------------------------------------ per-policy KPIs
def _escalation_workload(sim: dict) -> dict:
    log = sim.get("escalation_log", [])
    days = sim["hours"].normalize()
    first: dict[tuple, float | None] = {}
    for e in log:
        key = (e["agent_id"], days[e["t"]])
        if key not in first:
            first[key] = e["cost_bdt"]
    costed = [c for c in first.values() if c is not None]
    return {
        "escalation_events": len(log),
        "escalated_agent_days": len(first),
        "escalated_need_bdt": float(sum(e["unresolved_need"] for e in log)),
        "distributor_cost_proxy_every_escalation_bdt": round(sum(e["cost_bdt"] for e in log if e["cost_bdt"] is not None), 2),
        "distributor_cost_proxy_one_trip_per_agent_day_bdt": round(sum(costed), 2),
        "distributor_trips_cost_unavailable": len(first) - len(costed),
    }


def policy_kpis(sim: dict, counts: np.ndarray, ticket: np.ndarray, cluster_ticket: np.ndarray) -> dict:
    out_req, unmet = sim["out_req"], np.clip(sim["unmet"], 0.0, None)
    requested = float(out_req.sum())
    log = sim["log"]
    peer_cost = round(sum(x["logistics_cost"]["total_estimated_cost_bdt"] for x in log), 2) if log else 0.0
    return {
        "customer": {
            "requested_cash_out_bdt": requested,
            "served_cash_out_bdt": requested - float(unmet.sum()),
            "unmet_cash_out_bdt": float(unmet.sum()),
            "demand_fill_rate_pct": 100 * (1 - float(unmet.sum()) / requested) if requested else None,
            "shortage_agent_hours": int((unmet > 0.5).sum()),
            "requested_cash_out_transactions": int(np.asarray(counts).sum()),
            "estimated_failed_transactions": estimated_failed_transactions(unmet, ticket),
            "estimated_failed_transactions_method_b": estimated_failed_transactions(
                unmet, np.broadcast_to(cluster_ticket, unmet.shape)),
        },
        "operations": {
            "peer_transfers": len(log),
            "cash_moved_by_peer_transfers_bdt": float(sum(x["recommended_amount"] for x in log)),
            "peer_logistics_cost_bdt": peer_cost,
            "average_cost_per_peer_transfer_bdt": round(peer_cost / len(log), 2) if log else None,
            **_escalation_workload(sim),
        },
    }


def economics(value_protected: float, peer_cost: float, bps: float, extra_cost: float = 0.0) -> dict:
    gross = value_protected * bps / 10_000.0
    cost = peer_cost + extra_cost
    return {
        "agent_commission_bps": bps,
        "illustrative_commission_protected_bdt": round(gross, 2),
        "operational_logistics_cost_bdt": round(cost, 2),
        "net_illustrative_value_bdt": round(gross - cost, 2),
        "benefit_cost_ratio": _div(gross, cost),
        "break_even_commission_bps": _div(cost * 10_000.0, value_protected) if value_protected > 0 else None,
    }


def compare(base: dict, pol: dict, a: BusinessAssumptions) -> dict:
    """KPIs of ``pol`` relative to the status quo ``base`` (both from ``policy_kpis``)."""
    bc, pc, op = base["customer"], pol["customer"], pol["operations"]
    value = bc["unmet_cash_out_bdt"] - pc["unmet_cash_out_bdt"]
    tx_a = bc["estimated_failed_transactions"] - pc["estimated_failed_transactions"]
    tx_b = bc["estimated_failed_transactions_method_b"] - pc["estimated_failed_transactions_method_b"]
    peer = op["peer_logistics_cost_bdt"]
    dist_day = op["distributor_cost_proxy_one_trip_per_agent_day_bdt"]
    trips = op["escalated_agent_days"] - op["distributor_trips_cost_unavailable"]
    distributor = {
        "trips_one_per_escalated_agent_day": op["escalated_agent_days"],
        "logistics_cost_proxy_bdt": dist_day,
        "break_even_fee_per_trip_bdt": round(dist_day / trips, 2) if trips else None,
        "assumed_fee_per_trip_bdt": a.distributor_fee_per_trip_bdt,
        "illustrative_margin_bdt": (round(a.distributor_fee_per_trip_bdt * trips - dist_day, 2)
                                    if a.distributor_fee_per_trip_bdt is not None else None),
        "margin_note": (None if a.distributor_fee_per_trip_bdt is not None else
                        "No distributor fee assumption supplied, so no distributor profit is computed; "
                        "the break-even fee per trip is shown instead."),
    }
    return {
        "customer": {
            "cash_out_value_protected_bdt": value,
            "shortage_agent_hours_avoided": bc["shortage_agent_hours"] - pc["shortage_agent_hours"],
            "estimated_transactions_protected": tx_a,
            "estimated_transactions_protected_range": [min(tx_a, tx_b), max(tx_a, tx_b)],
            "fill_rate_gain_pp": ((pc["demand_fill_rate_pct"] or 0) - (bc["demand_fill_rate_pct"] or 0)),
        },
        "agent": {
            "cash_out_value_protected_bdt": value,
            "agent_commission_bps": a.agent_commission_bps,
            "illustrative_commission_protected_bdt": round(value * a.agent_commission_bps / 10_000.0, 2),
            "label": LABEL,
        },
        "distributor": distributor,
        "economics": {
            "peer_transfers_only": economics(value, peer, a.agent_commission_bps),
            "including_distributor_trips": economics(value, peer, a.agent_commission_bps, dist_day),
            "peer_cost_per_estimated_transaction_protected_bdt": _div(peer, tx_a) if tx_a > 0 else None,
            "peer_cost_per_bdt_1000_protected": _div(1000.0 * peer, value) if value > 0 else None,
            "roi": None,
            "roi_note": NOT_ROI,
            "label": LABEL,
        },
    }


def sensitivity(value_protected: float, peer_cost: float, a: BusinessAssumptions) -> dict:
    rows = []
    for m in a.sensitivity_cost_multipliers:
        for bps in a.sensitivity_commission_bps:
            e = economics(value_protected, peer_cost * m, bps)
            rows.append({"cost_multiplier": m, **e})
    return {
        "description": ("Net illustrative value = commission protected − peer logistics cost, for a grid of commission "
                        "rates and logistics-cost multipliers. The transfer plan is held fixed; only rates change."),
        "grid": rows,
        "break_even_commission_bps_by_cost_multiplier": [
            {"cost_multiplier": m,
             "break_even_commission_bps": economics(value_protected, peer_cost * m, a.agent_commission_bps)["break_even_commission_bps"]}
            for m in a.sensitivity_cost_multipliers],
        "label": LABEL,
    }


METRIC_DEFINITIONS = {
    "requested_cash_out_bdt": "Requested cash-out value in the held-out period (direct, synthetic).",
    "served_cash_out_bdt": "Requested minus unmet cash-out value under the policy (direct, simulated).",
    "unmet_cash_out_bdt": "Requested cash-out value not served because the agent lacked cash (direct, simulated).",
    "demand_fill_rate_pct": "Served ÷ requested cash-out value (direct, simulated).",
    "shortage_agent_hours": "Agent-hours with any unmet cash-out (direct, simulated; = Phase-1 shortage events).",
    "requested_cash_out_transactions": "Sum of the dataset's synthetic cash-out transaction counts (direct).",
    "estimated_failed_transactions": ("ESTIMATE. Σ unmet BDT ÷ the agent-hour's average synthetic cash-out ticket "
                                      "(cluster ticket if the hour has no counted transaction). Transaction-equivalents."),
    "estimated_failed_transactions_method_b": "ESTIMATE. Σ unmet BDT ÷ location-cluster ticket (cross-check).",
    "estimated_transactions_protected": "ESTIMATE. Status-quo minus policy estimated failed transactions (Method A).",
    "cash_out_value_protected_bdt": "Status-quo unmet minus policy unmet cash-out value (direct, simulated).",
    "illustrative_commission_protected_bdt": "ASSUMPTION-BASED. Cash-out value protected × agent_commission_bps ÷ 10,000.",
    "peer_logistics_cost_bdt": "Phase-2 synthetic operational-cost proxy summed over simulated peer transfers.",
    "escalated_agent_days": "Distinct agent-days with at least one escalation to distributor replenishment.",
    "distributor_cost_proxy_one_trip_per_agent_day_bdt": ("Phase-2 distributor-trip cost proxy, one trip per "
                                                          "escalated agent-day (from a synthetic district hub)."),
    "break_even_fee_per_trip_bdt": "Distributor logistics-cost proxy ÷ trips: the fee per trip needed to cover it.",
    "net_illustrative_value_bdt": "Illustrative commission protected minus operational logistics cost.",
    "benefit_cost_ratio": "Illustrative commission protected ÷ operational logistics cost (not an ROI).",
    "break_even_commission_bps": "Commission rate at which commission protected equals the logistics cost.",
}

LIMITATIONS = [
    "Synthetic data only: no upay revenue, commission, customer, cost or saving is measured or claimed.",
    "Transaction counts protected are estimates (transaction-equivalents); the simulator removes value, not "
    "individual transactions, and assumes declined requests have the hour's average ticket size.",
    "The agent commission rate is an illustrative assumption, not upay's or any provider's rate.",
    "Customers are assumed not to retry or switch agents; unmet demand may be partly recovered in reality.",
    "Distributor escalations are not delivered in the simulation, so their cost is shown but their benefit is not.",
    "Logistics costs use the Phase-2 synthetic operational-cost proxy; the sensitivity grid re-prices a fixed "
    "transfer plan and does not re-optimise it.",
    "No ROI, retention or lifetime-value claim is made.",
]


def derive(kpis: dict, a: BusinessAssumptions) -> tuple[dict, dict]:
    """Assumption-dependent results from the direct per-policy KPIs."""
    base = kpis["status_quo"]
    vs = {k: compare(base, kpis[k], a) for k in kpis if k != "status_quo"}
    sens = {k: sensitivity(vs[k]["customer"]["cash_out_value_protected_bdt"], kpis[k]["operations"]["peer_logistics_cost_bdt"], a)
            for k in ("agentflow_v1", "agentflow_v2") if k in vs}
    return vs, sens


def _assumption_block(a: BusinessAssumptions) -> dict:
    return {**asdict(a), "label": LABEL,
            "agent_commission_note": ("Illustrative round number on served cash-out value; not upay's or "
                                      "any provider's commission rate."),
            "logistics_cost_source": logistics.ASSUMPTION_LABEL,
            "logistics_assumptions": asdict(logistics.DEFAULT_CONFIG),
            "override": f"set {ENV_PREFIX}AGENT_COMMISSION_BPS / {ENV_PREFIX}DISTRIBUTOR_FEE_PER_TRIP_BDT"}


def reprice(artifact: dict, a: BusinessAssumptions) -> dict:
    """Re-derive the assumption-based figures for new rates without re-running the simulation."""
    out = {**artifact, "assumptions": _assumption_block(a)}
    vs, sens = derive(artifact["calculations"]["policies"], a)
    out["calculations"] = {**artifact["calculations"], "vs_status_quo": vs}
    out["sensitivity"] = sens
    return out


def compute(sims: dict, counts: np.ndarray, cluster_ticket: np.ndarray, a: BusinessAssumptions | None = None) -> dict:
    """Pure calculation from simulated policies (``impact.simulate_policy`` outputs)."""
    a = a or BusinessAssumptions()
    any_sim = sims["status_quo"]
    ticket, fallback = ticket_matrix(any_sim["out_req"], counts, cluster_ticket)
    kpis = {k: policy_kpis(s, counts, ticket, cluster_ticket) for k, s in sims.items()}
    vs, sens = derive(kpis, a)
    unmet_sq = np.clip(any_sim["unmet"], 0, None)
    return {
        "label": LABEL,
        "version": VERSION,
        "version_note": VERSION_NOTE,
        "synthetic_data": True,
        "simulated_estimate": True,
        "product_story": "Same liquidity. Placed ahead of demand.",
        "period": {"start": str(any_sim["hours"][0]), "end": str(any_sim["hours"][-1]),
                   "hours": len(any_sim["hours"]), "agents": len(any_sim["agent_ids"])},
        "assumptions": _assumption_block(a),
        "methodology": {
            "direct": ["requested/served/unmet cash-out value", "fill rate", "shortage agent-hours",
                       "requested cash-out transaction counts", "peer transfers", "escalation events and agent-days",
                       "cash moved"],
            "estimated": ["failed and protected cash-out transactions (transaction-equivalents)"],
            "assumption_based": ["illustrative agent commission protected", "net illustrative value",
                                 "benefit-cost ratio", "distributor margin (only if a fee is supplied)"],
            "cost_proxy": ["peer and distributor logistics cost (Phase-2 synthetic operational-cost proxy)"],
            "transaction_estimate": ("Method A: unmet BDT ÷ the agent-hour's own average cash-out ticket (cash-out "
                                     "amount ÷ count), cluster ticket where the hour has no counted transaction. "
                                     "Method B: unmet BDT ÷ cluster ticket everywhere. Range = [min, max] of A and B."),
            "fallback_ticket_share_of_status_quo_unmet_pct": (
                100 * float(unmet_sq[fallback].sum()) / float(unmet_sq.sum()) if unmet_sq.sum() else 0.0),
            "roi_note": NOT_ROI,
        },
        "metric_definitions": METRIC_DEFINITIONS,
        "policy_labels": POLICY_LABELS,
        "calculations": {"policies": kpis, "vs_status_quo": vs},
        "sensitivity": sens,
        "limitations": LIMITATIONS,
    }


def run(feats: pd.DataFrame, agents: pd.DataFrame, preds: pd.DataFrame, hist_rate: pd.Series,
        anomaly_status: pd.DataFrame | None = None, v2_cfg: rebalance_v2.RebalanceV2Config | None = None,
        a: BusinessAssumptions | None = None) -> dict:
    v2_cfg = v2_cfg or rebalance_v2.selected_config()
    sim = lambda **kw: impact.simulate_policy(feats, agents, preds, hist_rate, anomaly_status, **kw)
    sims = {
        "status_quo": impact.simulate_policy(feats, agents, None, hist_rate, forecast_source="none"),
        "agentflow_v1": sim(forecast_source="ml", policy="v1"),
        "agentflow_v2": sim(forecast_source="ml", policy="v2",
                            policy_cfg=replace(v2_cfg, ranking_cost_model=rebalance_v2.SERVING_RANKING_COST_MODEL)),
        "agentflow_v2_logistics_ranking_experiment": sim(
            forecast_source="ml", policy="v2",
            policy_cfg=replace(v2_cfg, ranking_cost_model=rebalance_v2.EXPERIMENT_RANKING_COST_MODEL)),
    }
    s0 = sims["status_quo"]
    mats, _ = impact._matrices(feats, s0["agent_ids"], s0["hours"], ["cash_out_count"])
    cluster = agents.set_index("agent_id").reindex(s0["agent_ids"])["location_cluster"]
    cluster_ticket = cluster.map(data_gen.OUT_TICKET).to_numpy(float)[None, :]
    return compute(sims, np.nan_to_num(mats["cash_out_count"]), cluster_ticket, a or assumptions_from_env())


def reconcile(biz: dict, imp: dict) -> dict:
    """Cross-check against impact.json so the business layer provably reuses the same simulations."""
    p, p2 = imp["policies"], imp.get("phase2_logistics", {}).get("policies", {})
    bp = biz["calculations"]["policies"]
    checks = {
        "status_quo_unmet": (biz["calculations"]["policies"]["status_quo"]["customer"]["unmet_cash_out_bdt"], p["status_quo"]["unmet_cash_demand_bdt"]),
        "v1_unmet": (biz["calculations"]["policies"]["agentflow_v1"]["customer"]["unmet_cash_out_bdt"], p["agentflow"]["unmet_cash_demand_bdt"]),
        "v2_unmet": (bp["agentflow_v2"]["customer"]["unmet_cash_out_bdt"], p["agentflow_v2"]["unmet_cash_demand_bdt"]),
        "v2_shortage_events": (bp["agentflow_v2"]["customer"]["shortage_agent_hours"], p["agentflow_v2"]["shortage_events"]),
        "v2_transfers": (bp["agentflow_v2"]["operations"]["peer_transfers"], p["agentflow_v2"]["interventions"]),
    }
    if "agentflow_v2" in p2:
        checks["v2_peer_logistics_cost"] = (bp["agentflow_v2"]["operations"]["peer_logistics_cost_bdt"],
                                            p2["agentflow_v2"]["peer_transfer_logistics_cost_bdt"])
    exp = p2.get("agentflow_v2_logistics_ranking_experiment")
    if exp and "agentflow_v2_logistics_ranking_experiment" in bp:
        e = bp["agentflow_v2_logistics_ranking_experiment"]
        checks["experiment_shortage_events"] = (e["customer"]["shortage_agent_hours"], exp["shortage_events"])
        checks["experiment_peer_logistics_cost"] = (e["operations"]["peer_logistics_cost_bdt"], exp["peer_transfer_logistics_cost_bdt"])
    return {k: {"business_layer": a, "impact_json": b, "match": abs(float(a) - float(b)) < 0.01} for k, (a, b) in checks.items()}
