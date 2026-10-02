"""Phase 2D: ML attribution baselines for morning prepositioning (research only).

Pre-registered in docs/ML_ATTRIBUTION_PROTOCOL.md. Every operational policy uses the same district
budgets, the same BDT 5,000 floors and the same allocator code (``prepositioning.allocate_resource``);
only the allocation SIGNAL differs. History signals use only the previous 7 complete operational days
(08:00 -> 07:59), all fully observed at the 08:00 decision.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import prepositioning as pp

SEEDS = (2026, 2027, 2028, 2029, 2030)
HISTORY_DAYS = 7
SIMPLE_BASELINES = ("history_proportional", "seasonal_requirement_7d")
ML_POLICY = "agentflow_ml_p90"
OPERATIONAL_POLICIES = ("status_quo",) + SIMPLE_BASELINES + (ML_POLICY,)
ORACLE_POLICIES = ("oracle_6h", "oracle_full_day")
BAR = {"min_seeds_ml_not_worse": 4, "min_median_incremental_combined_pct": 5.0,
       "max_side_increase_pct": 5.0, "max_seeds_with_side_increase": 1}
MODES = {"history_proportional": "proportional", "seasonal_requirement_7d": "need",
         ML_POLICY: "need", "oracle_6h": "need", "oracle_full_day": "need"}


# ---------------------------------------------------------------- history signals
def prior_day_windows(day: pd.Timestamp, n: int = HISTORY_DAYS) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    """[start, end) of the previous n complete operational days for the morning plan of ``day``."""
    decision = day + pd.Timedelta(hours=pp.DECISION_HOUR)
    wins = [(decision - pd.Timedelta(days=k), decision - pd.Timedelta(days=k - 1)) for k in range(n, 0, -1)]
    assert all(end <= decision for _, end in wins)
    return wins


def peak_requirements(req_out: np.ndarray, req_in: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Realised peak cash and e-float requirement over a window (rows = hours, cols = agents)."""
    if len(req_out) == 0:
        z = np.zeros(req_out.shape[1])
        return z, z
    net = np.cumsum(req_out - req_in, axis=0)
    return np.maximum(net.max(axis=0), 0.0), np.maximum((-net).max(axis=0), 0.0)


def history_signals(req_out: np.ndarray, req_in: np.ndarray, hours: pd.DatetimeIndex, day: pd.Timestamp) -> dict:
    """Per-agent 7-day history signals for the plan of ``day`` (only data strictly before 08:00 of ``day``)."""
    outs, ins, pc, pe = [], [], [], []
    for start, end in prior_day_windows(day):
        m = np.asarray((hours >= start) & (hours < end))
        if m.sum() != 24:
            raise ValueError(f"incomplete history window {start} .. {end}")
        outs.append(req_out[m].sum(axis=0))
        ins.append(req_in[m].sum(axis=0))
        c, e = peak_requirements(req_out[m], req_in[m])
        pc.append(c)
        pe.append(e)
    return {"avg_daily_cash_out": np.mean(outs, axis=0), "avg_daily_cash_in": np.mean(ins, axis=0),
            "avg_peak_cash_requirement": np.mean(pc, axis=0), "avg_peak_efloat_requirement": np.mean(pe, axis=0)}


# ---------------------------------------------------------------- allocation (same allocator for all)
def allocate(agents: pd.DataFrame, cash_signal, efloat_signal, mode: str) -> tuple[np.ndarray, np.ndarray, int]:
    """Allocate both resources per district with ``prepositioning.allocate_resource``.

    ``agents`` must be in agent_id order with columns agent_id, district, target_cash_level,
    target_efloat_level. mode "need": signal in the need (P90) slot, status-quo targets as leftover
    weights (identical to the Phase 2C allocator). mode "proportional": zero need, signal as the
    proportional weights. Returns arrays in agent order plus the floor edge-case count.
    """
    assert mode in ("need", "proportional")
    ids = agents["agent_id"].to_numpy()
    assert (ids[:-1] < ids[1:]).all(), "agents must be in agent_id order"
    cs, es = np.asarray(cash_signal, float), np.asarray(efloat_signal, float)
    tc = agents["target_cash_level"].round().astype(np.int64).to_numpy()
    te = agents["target_efloat_level"].round().astype(np.int64).to_numpy()
    ac, ae = np.zeros(len(ids), np.int64), np.zeros(len(ids), np.int64)
    edges = 0
    for _, idx in agents.groupby("district", sort=True).indices.items():
        for sig, sq, out, floor in ((cs, tc, ac, pp.FLOOR_CASH_BDT), (es, te, ae, pp.FLOOR_EFLOAT_BDT)):
            if mode == "need":
                a, e = pp.allocate_resource(ids[idx], int(sq[idx].sum()), sig[idx], sq[idx], floor)
            else:
                a, e = pp.allocate_resource(ids[idx], int(sq[idx].sum()), np.zeros(len(idx)), sig[idx], floor)
            out[idx] = a
            edges += int(e)
    return ac, ae, edges


# ---------------------------------------------------------------- comparison and bar
def reduction_pct(new: float, ref: float) -> float:
    return 100.0 * (ref - new) / ref if ref else 0.0


def best_simple(metrics: dict) -> str:
    """Lower combined unmet among the simple baselines (ties -> history_proportional)."""
    return min(SIMPLE_BASELINES, key=lambda k: (metrics[k]["combined_unmet_bdt"], SIMPLE_BASELINES.index(k)))


def incremental(ml: dict, best: dict) -> dict:
    return {"combined_unmet_reduction_pct": reduction_pct(ml["combined_unmet_bdt"], best["combined_unmet_bdt"]),
            "cash_unmet_reduction_pct": reduction_pct(ml["unmet_cash_out_bdt"], best["unmet_cash_out_bdt"]),
            "efloat_unmet_reduction_pct": reduction_pct(ml["unmet_cash_in_bdt"], best["unmet_cash_in_bdt"]),
            "shortage_event_difference": int(ml["shortage_events_total"] - best["shortage_events_total"])}


def ml_value_bar(per_seed: dict) -> dict:
    """Pre-registered rule. per_seed[s] needs: incremental (dict), conserved_all_policies (bool)."""
    inc = {s: r["incremental"] for s, r in per_seed.items()}
    not_worse = sum(i["combined_unmet_reduction_pct"] >= 0 for i in inc.values())
    med = float(np.median([i["combined_unmet_reduction_pct"] for i in inc.values()]))
    side_inc = sum((i["cash_unmet_reduction_pct"] < -BAR["max_side_increase_pct"]) or
                   (i["efloat_unmet_reduction_pct"] < -BAR["max_side_increase_pct"]) for i in inc.values())
    conserved = all(r["conserved_all_policies"] for r in per_seed.values())
    checks = {"ml_not_worse_in_4_of_5": not_worse >= BAR["min_seeds_ml_not_worse"],
              "median_incremental_ge_5pct": med >= BAR["min_median_incremental_combined_pct"],
              "exact_conservation_all": conserved,
              "side_increase_gt5pct_in_at_most_1_seed": side_inc <= BAR["max_seeds_with_side_increase"]}
    return {"seeds_ml_not_worse": int(not_worse), "median_incremental_combined_reduction_pct": med,
            "seeds_with_side_increase_gt5pct": int(side_inc), "checks": checks, "passes": bool(all(checks.values()))}
