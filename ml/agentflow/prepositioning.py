"""Phase 2C: forecast-guided dual-liquidity prepositioning (research only).

Pre-registered in docs/PREPOSITIONING_PROTOCOL.md. At 08:00 each held-out day the SAME district
cash and e-float budgets as the status quo are redistributed across agents using the 6-hour P90
forecasts available at 07:00. Integer-BDT arithmetic makes conservation exact. The day is then
replayed with the same requested flows through the resource-conserving ``serve_hour`` rule.
No working capital is added, no transfer is executed, and the allocator reads no outcome labels.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .dual_world import OPENING_HOUR, serve_hour

# ---------------------------------------------------------------- pre-registered constants
SEEDS = (2026, 2027, 2028, 2029, 2030)
FLOOR_CASH_BDT = 5_000
FLOOR_EFLOAT_BDT = 5_000
DECISION_HOUR = OPENING_HOUR  # 08:00 reset
FORECAST_ROW_HOUR = 7  # row at end of hour 07 -> forecast for 08:00-13:59
BETTER_WORSE_TOLERANCE_BDT = 1.0
CONCENTRATION_FLAG = (0.5, 2.0)
BAR = {"max_side_unmet_increase_pct": 2.0, "min_seeds_passing": 4, "min_seeds_reducing_combined": 4,
       "min_median_combined_reduction_pct": 5.0}

OPERATIONAL_COLUMNS = ["agent_id", "district", "target_cash_level", "target_efloat_level",
                       "pred_net_requirement_p90_6h", "pred_efloat_requirement_p90_6h"]


# ---------------------------------------------------------------- allocator
def largest_remainder(total: int, weights) -> np.ndarray:
    """Split integer ``total`` in proportion to ``weights`` into integers summing exactly to ``total``.

    Ties in the fractional remainder go to the earlier index (callers pass agents in agent_id order).
    """
    total = int(total)
    w = np.maximum(np.asarray(weights, float), 0.0)
    if total <= 0:
        return np.zeros(len(w), dtype=np.int64)
    if w.sum() <= 0:
        w = np.ones(len(w))
    exact = total * w / w.sum()
    base = np.floor(exact).astype(np.int64)
    rem = total - int(base.sum())
    if rem > 0:
        frac = exact - base
        order = np.lexsort((np.arange(len(w)), -frac))  # largest remainder, then index
        base[order[:rem]] += 1
    return base


def allocate_resource(agent_ids, budget: int, p90, sq_targets, floor: int) -> tuple[np.ndarray, bool]:
    """Allocate one district's budget for one resource. Returns (integer allocation, floor_edge_case).

    Agents must be passed in agent_id ascending order.
    """
    ids = np.asarray(agent_ids)
    assert (ids[:-1] <= ids[1:]).all(), "agents must be in agent_id order"
    n = len(ids)
    budget = int(budget)
    if budget < n * floor:
        return largest_remainder(budget, sq_targets), True
    alloc = np.full(n, floor, dtype=np.int64)
    remaining = budget - n * floor
    need = np.ceil(np.maximum(np.asarray(p90, float) - floor, 0.0)).astype(np.int64)
    for i in np.lexsort((np.arange(n), -need)):  # largest need first, ties by agent_id
        if remaining <= 0:
            break
        give = min(int(need[i]), remaining)
        alloc[i] += give
        remaining -= give
    if remaining > 0:
        alloc += largest_remainder(remaining, sq_targets)
    return alloc, False


def allocate_day(view: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Allocate both resources for every district at one 08:00 decision (OPERATIONAL_COLUMNS only)."""
    v = view[OPERATIONAL_COLUMNS].sort_values("agent_id", kind="stable").reset_index(drop=True)
    out, edges = [], 0
    for district, g in v.groupby("district", sort=True):
        ids = g["agent_id"].to_numpy()
        tc = g["target_cash_level"].round().astype(np.int64).to_numpy()
        te = g["target_efloat_level"].round().astype(np.int64).to_numpy()
        ac, ec = allocate_resource(ids, int(tc.sum()), g["pred_net_requirement_p90_6h"].to_numpy(), tc, FLOOR_CASH_BDT)
        ae, ee = allocate_resource(ids, int(te.sum()), g["pred_efloat_requirement_p90_6h"].to_numpy(), te, FLOOR_EFLOAT_BDT)
        edges += int(ec) + int(ee)
        out.append(pd.DataFrame({"agent_id": ids, "district": district, "alloc_cash": ac, "alloc_efloat": ae,
                                 "sq_cash": tc, "sq_efloat": te}))
    return pd.concat(out, ignore_index=True), edges


# ---------------------------------------------------------------- replay
def replay(req_out: np.ndarray, req_in: np.ndarray, hours: pd.DatetimeIndex, init_cash, init_efloat,
           alloc_cash: dict, alloc_efloat: dict) -> dict:
    """Replay requested flows (n_hours x n_agents). At each 08:00 the balances are set to that day's
    allocation (dict: date -> array in agent order). Returns served/unmet/balance arrays."""
    n_h, n_a = req_out.shape
    cash = np.asarray(init_cash, float).copy()
    ef = np.asarray(init_efloat, float).copy()
    out = {k: np.zeros((n_h, n_a)) for k in ("served_out", "served_in", "unmet_out", "unmet_in", "cash", "efloat")}
    for t, ts in enumerate(hours):
        if ts.hour == DECISION_HOUR:
            d = ts.normalize()
            cash = np.asarray(alloc_cash[d], float).copy()
            ef = np.asarray(alloc_efloat[d], float).copy()
        so, si, cash, ef = serve_hour(cash, ef, req_out[t], req_in[t])
        out["served_out"][t], out["served_in"][t] = so, si
        out["unmet_out"][t], out["unmet_in"][t] = req_out[t] - so, req_in[t] - si
        out["cash"][t], out["efloat"][t] = cash, ef
    return out


def service_metrics(sim: dict, req_out: np.ndarray, req_in: np.ndarray, mask: np.ndarray) -> dict:
    uo, ui = sim["unmet_out"][mask], sim["unmet_in"][mask]
    ro, ri = req_out[mask], req_in[mask]
    ce, ee = uo > 0, ui > 0
    return {"cash_shortage_events": int(ce.sum()), "unmet_cash_out_bdt": float(uo.sum()),
            "cash_out_fill_rate": float(1 - uo.sum() / max(ro.sum(), 1)),
            "efloat_shortage_events": int(ee.sum()), "unmet_cash_in_bdt": float(ui.sum()),
            "cash_in_fill_rate": float(1 - ui.sum() / max(ri.sum(), 1)),
            "fully_serviceable_agent_hours": int((~ce & ~ee).sum()), "agent_hours": int(ce.size),
            "combined_unmet_bdt": float(uo.sum() + ui.sum()),
            "combined_fill_rate": float(1 - (uo.sum() + ui.sum()) / max(ro.sum() + ri.sum(), 1)),
            "shortage_events_total": int(ce.sum() + ee.sum()),
            "agents_with_any_shortage": int(((ce | ee).any(axis=0)).sum())}


def pct_change(new: float, old: float) -> float:
    return 100.0 * (new - old) / old if old else 0.0


def seed_bar(sq: dict, af: dict, conserved: bool) -> dict:
    side_c = pct_change(af["unmet_cash_out_bdt"], sq["unmet_cash_out_bdt"])
    side_e = pct_change(af["unmet_cash_in_bdt"], sq["unmet_cash_in_bdt"])
    checks = {"combined_unmet_not_increased": af["combined_unmet_bdt"] <= sq["combined_unmet_bdt"],
              "cash_unmet_increase_within_2pct": side_c <= BAR["max_side_unmet_increase_pct"],
              "efloat_unmet_increase_within_2pct": side_e <= BAR["max_side_unmet_increase_pct"],
              "resources_exactly_conserved": bool(conserved)}
    return {"checks": checks, "passes": bool(all(checks.values()))}


def overall_bar(per_seed: dict) -> dict:
    red = [per_seed[s]["impact"]["combined_unmet_reduction_pct"] for s in per_seed]
    passing = sum(per_seed[s]["bar"]["passes"] for s in per_seed)
    reducing = sum(per_seed[s]["impact"]["combined_unmet_reduction_pct"] > 0 for s in per_seed)
    conserved = all(per_seed[s]["conservation"]["exact"] for s in per_seed)
    med = float(np.median(red))
    checks = {"seeds_passing": passing >= BAR["min_seeds_passing"],
              "seeds_reducing_combined": reducing >= BAR["min_seeds_reducing_combined"],
              "median_combined_reduction": med >= BAR["min_median_combined_reduction_pct"],
              "conservation_all_seeds": conserved}
    return {"seeds_passing": int(passing), "seeds_reducing_combined": int(reducing),
            "median_combined_reduction_pct": med, "checks": checks, "passes": bool(all(checks.values()))}
