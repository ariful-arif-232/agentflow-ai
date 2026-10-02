"""Phase 2B-0: read-only complementarity feasibility audit for the Dual-Liquidity World v2.

Pre-registered in docs/DUAL_COMPLEMENTARITY_PROTOCOL.md. Measures whether *safe, local and
simultaneous* complementary counterparties exist:

* agent A (cash-pressure side) needs physical cash and holds safe surplus e-float;
* agent B (e-float-pressure side) needs e-float and holds safe surplus cash;
* same district, <= 15 km apart.

A hypothetical swap of x (x cash B->A, x e-float A->B) conserves network cash and network e-float.
Nothing here executes, recommends or simulates a swap, and no business impact is computed.
Operational pairing reads predictions and current balances only (``OPERATIONAL_COLUMNS``).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .rebalance import haversine_km

# ---------------------------------------------------------------- pre-registered constants
SEEDS = (2026, 2027, 2028, 2029, 2030)
DECISION_HOURS = (9, 11, 13, 15, 17, 19)
APPENDIX_HOURS = tuple(range(8, 22))
MAX_DISTANCE_KM = 15.0
MIN_SWAP_BDT = 2_000.0
ROUNDING_BDT = 500.0
RESERVE_FLOOR_BDT = 5_000.0
RESERVE_MULTIPLIER = 1.10
ANOMALY_LOOKBACK_H = 6
USEFUL_DISTRICT_MIN_PAIRS = 10
BAR = {"min_distinct_agents": 20, "min_viable_pairs": 100,
       "min_cash_side_share_with_counterparty": 0.10, "min_efloat_side_share_with_counterparty": 0.10}
MIN_WORLDS_PASSING = 4
KEY_METRICS = ("cash_side_share_with_counterparty", "efloat_side_share_with_counterparty", "viable_pairs",
               "greedy_swappable_bdt", "cash_need_coverable_pct", "efloat_need_coverable_pct")

OPERATIONAL_COLUMNS = [
    "agent_id", "timestamp", "district", "synthetic_latitude", "synthetic_longitude",
    "cash_balance", "efloat_balance",
    "pred_net_requirement_6h", "pred_net_requirement_p90_6h",
    "pred_efloat_requirement_6h", "pred_efloat_requirement_p90_6h",
    "behaviour_status",
]


# ---------------------------------------------------------------- reserves and capacity
def protected_reserve(p90):
    return np.maximum(RESERVE_FLOOR_BDT, RESERVE_MULTIPLIER * np.maximum(np.asarray(p90, float), 0.0))


def safe_surplus(balance, p90):
    return np.maximum(np.asarray(balance, float) - protected_reserve(p90), 0.0)


def round_down(x):
    return np.floor(np.asarray(x, float) / ROUNDING_BDT) * ROUNDING_BDT


def swap_capacity(a_cash_need, b_efloat_need, a_efloat_surplus, b_cash_surplus):
    """Raw 1:1 swap capacity for an (A, B) pair: the binding minimum of the four quantities."""
    return np.minimum.reduce([np.asarray(a_cash_need, float), np.asarray(b_efloat_need, float),
                              np.asarray(a_efloat_surplus, float), np.asarray(b_cash_surplus, float)])


def viable_amount(capacity):
    """Rounded-down amount, or 0 if below the minimum meaningful swap."""
    amt = round_down(capacity)
    return np.where(amt >= MIN_SWAP_BDT, amt, 0.0)


def hypothetical_swap(cash: dict, efloat: dict, a: str, b: str, x: float) -> tuple[dict, dict]:
    """Return NEW balance dicts after a hypothetical swap (x cash B->A, x e-float A->B). Never executed."""
    cash, efloat = dict(cash), dict(efloat)
    cash[b] -= x
    cash[a] += x
    efloat[a] -= x
    efloat[b] += x
    return cash, efloat


# ---------------------------------------------------------------- operational view
def operational_view(snap: pd.DataFrame) -> pd.DataFrame:
    """Derived needs/surpluses/eligibility from OPERATIONAL_COLUMNS only (no labels, no future)."""
    s = snap[OPERATIONAL_COLUMNS].sort_values(["timestamp", "agent_id"], kind="stable").reset_index(drop=True)
    s["cash_need"] = np.maximum(s["pred_net_requirement_6h"] - s["cash_balance"], 0.0)
    s["efloat_need"] = np.maximum(s["pred_efloat_requirement_6h"] - s["efloat_balance"], 0.0)
    s["cash_surplus"] = safe_surplus(s["cash_balance"], s["pred_net_requirement_p90_6h"])
    s["efloat_surplus"] = safe_surplus(s["efloat_balance"], s["pred_efloat_requirement_p90_6h"])
    s["normal"] = s["behaviour_status"] == "NORMAL"
    s["cash_side"] = s["cash_need"] > 0
    s["efloat_side"] = s["efloat_need"] > 0
    s["a_eligible"] = s["cash_side"] & s["normal"] & (s["efloat_surplus"] > 0)
    s["b_eligible"] = s["efloat_side"] & s["normal"] & (s["cash_surplus"] > 0)
    return s


def candidate_pairs(view: pd.DataFrame) -> pd.DataFrame:
    """All same-district (A, B) pairs at one decision time with distance and capacity."""
    cols = ["timestamp", "district", "a", "b", "distance_km", "capacity", "amount", "viable"]
    A = view[view["a_eligible"]]
    B = view[view["b_eligible"]]
    if A.empty or B.empty:
        return pd.DataFrame(columns=cols)
    m = A.merge(B, on=["timestamp", "district"], suffixes=("_a", "_b"))
    if m.empty:
        return pd.DataFrame(columns=cols)
    dist = haversine_km(m["synthetic_latitude_a"], m["synthetic_longitude_a"],
                        m["synthetic_latitude_b"], m["synthetic_longitude_b"])
    cap = swap_capacity(m["cash_need_a"], m["efloat_need_b"], m["efloat_surplus_a"], m["cash_surplus_b"])
    out = pd.DataFrame({"timestamp": m["timestamp"], "district": m["district"], "a": m["agent_id_a"],
                        "b": m["agent_id_b"], "distance_km": np.asarray(dist), "capacity": cap})
    out = out[out["distance_km"] <= MAX_DISTANCE_KM].copy()
    out["amount"] = viable_amount(out["capacity"])
    out["viable"] = out["amount"] >= MIN_SWAP_BDT
    return out.sort_values(["timestamp", "a", "b"]).reset_index(drop=True)[cols]


def greedy_allocate(view: pd.DataFrame, pairs: pd.DataFrame) -> pd.DataFrame:
    """Conservative feasibility allocation at ONE decision time (not V3, not a policy).

    Highest own-P50-gap first (both sides), nearest valid counterparty first; needs and surpluses are
    decremented so each BDT of capacity is used at most once.
    """
    cols = ["timestamp", "a", "b", "distance_km", "amount"]
    pr = pairs[pairs["distance_km"] <= MAX_DISTANCE_KM]
    if pr.empty:
        return pd.DataFrame(columns=cols)
    v = view.set_index("agent_id")
    a_need = v["cash_need"].to_dict()
    a_sur = v["efloat_surplus"].to_dict()
    b_need = v["efloat_need"].to_dict()
    b_sur = v["cash_surplus"].to_dict()
    nbr: dict[str, list[tuple[float, str, str]]] = {}
    for a, b, d in zip(pr["a"], pr["b"], pr["distance_km"]):
        nbr.setdefault(a, []).append((float(d), b, "B"))
        nbr.setdefault(b, []).append((float(d), a, "A"))
    a_set = set(pr["a"])
    order = sorted(nbr, key=lambda ag: (-(a_need[ag] if ag in a_set else b_need[ag]), ag))
    ts = pr["timestamp"].iloc[0]
    rows = []
    for ag in order:
        for d, other, _ in sorted(nbr[ag], key=lambda t: (t[0], t[1])):
            a, b = (ag, other) if ag in a_set else (other, ag)
            x = float(round_down(min(a_need[a], b_need[b], a_sur[a], b_sur[b])))
            if x < MIN_SWAP_BDT:
                continue
            a_need[a] -= x
            a_sur[a] -= x
            b_need[b] -= x
            b_sur[b] -= x
            rows.append((ts, a, b, d, x))
    return pd.DataFrame(rows, columns=cols)


def no_counterparty_reasons(view: pd.DataFrame, pairs: pd.DataFrame, side: str) -> dict:
    """Why pressure rows on one side have no viable counterparty (mutually exclusive, first match)."""
    is_a = side == "cash"
    press = view[view["cash_side" if is_a else "efloat_side"]]
    own_sur = "efloat_surplus" if is_a else "cash_surplus"
    elig_other = view[view["b_eligible" if is_a else "a_eligible"]]
    key, other = ("a", "b") if is_a else ("b", "a")
    viable = set(map(tuple, pairs.loc[pairs["viable"], ["timestamp", key]].to_numpy()))
    within = set(map(tuple, pairs[["timestamp", key]].to_numpy()))
    other_d = set(map(tuple, elig_other[["timestamp", "district"]].to_numpy()))
    reasons = {"has_viable_counterparty": 0, "not_normal_behaviour": 0, "no_own_safe_surplus": 0,
               "no_eligible_opposite_agent_in_district": 0, "none_within_15km": 0, "capacity_below_minimum": 0}
    for r in press.itertuples(index=False):
        k = (r.timestamp, r.agent_id)
        if k in viable:
            reasons["has_viable_counterparty"] += 1
        elif not r.normal:
            reasons["not_normal_behaviour"] += 1
        elif getattr(r, own_sur) <= 0:
            reasons["no_own_safe_surplus"] += 1
        elif (r.timestamp, r.district) not in other_d:
            reasons["no_eligible_opposite_agent_in_district"] += 1
        elif k not in within:
            reasons["none_within_15km"] += 1
        else:
            reasons["capacity_below_minimum"] += 1
    return reasons


def analyse(snaps: pd.DataFrame) -> dict:
    """Availability + greedy feasibility over decision rows ``snaps`` (one row per agent per timestamp)."""
    view = operational_view(snaps)
    pairs = pd.concat([candidate_pairs(g) for _, g in view.groupby("timestamp", sort=True)], ignore_index=True)
    viable = pairs[pairs["viable"]] if len(pairs) else pairs
    alloc = pd.concat([greedy_allocate(g, pairs[pairs["timestamp"] == ts])
                       for ts, g in view.groupby("timestamp", sort=True)], ignore_index=True)
    cash_rows, ef_rows = view[view["cash_side"]], view[view["efloat_side"]]
    a_with = set(map(tuple, viable[["timestamp", "a"]].to_numpy())) if len(viable) else set()
    b_with = set(map(tuple, viable[["timestamp", "b"]].to_numpy())) if len(viable) else set()
    cash_need, ef_need = float(cash_rows["cash_need"].sum()), float(ef_rows["efloat_need"].sum())
    swapped = float(alloc["amount"].sum()) if len(alloc) else 0.0
    a_agents = set(viable["a"]) if len(viable) else set()
    b_agents = set(viable["b"]) if len(viable) else set()
    by_district = {}
    for dist in sorted(view["district"].unique()):
        vd = view[view["district"] == dist]
        pdv = viable[viable["district"] == dist] if len(viable) else viable
        ad = alloc[alloc["a"].isin(vd["agent_id"])] if len(alloc) else alloc
        cn, en = float(vd.loc[vd["cash_side"], "cash_need"].sum()), float(vd.loc[vd["efloat_side"], "efloat_need"].sum())
        sw = float(ad["amount"].sum()) if len(ad) else 0.0
        by_district[str(dist)] = {"agents": int(vd["agent_id"].nunique()),
                                  "cash_pressure_rows": int(vd["cash_side"].sum()),
                                  "efloat_pressure_rows": int(vd["efloat_side"].sum()),
                                  "viable_pairs": int(len(pdv)), "greedy_swappable_bdt": sw,
                                  "cash_need_coverable_pct": 100 * sw / cn if cn else None,
                                  "efloat_need_coverable_pct": 100 * sw / en if en else None}
    return {
        "decision_timestamps": int(view["timestamp"].nunique()),
        "decision_rows": int(len(view)),
        "cash_pressure_rows": int(len(cash_rows)), "efloat_pressure_rows": int(len(ef_rows)),
        "cash_side_eligible_rows": int(view["a_eligible"].sum()), "efloat_side_eligible_rows": int(view["b_eligible"].sum()),
        "cash_rows_with_counterparty": len(a_with), "efloat_rows_with_counterparty": len(b_with),
        "cash_side_share_with_counterparty": len(a_with) / max(len(cash_rows), 1),
        "efloat_side_share_with_counterparty": len(b_with) / max(len(ef_rows), 1),
        "no_counterparty_reasons": {"cash": no_counterparty_reasons(view, pairs, "cash"),
                                    "efloat": no_counterparty_reasons(view, pairs, "efloat")},
        "distinct_agents": {"cash_side": len(a_agents), "efloat_side": len(b_agents), "total": len(a_agents | b_agents)},
        "candidate_pairs_within_15km": int(len(pairs)), "viable_pairs": int(len(viable)),
        "raw_viable_pair_capacity_bdt_double_counted": float(viable["amount"].sum()) if len(viable) else 0.0,
        "total_p50_cash_need_bdt": cash_need, "total_p50_efloat_need_bdt": ef_need,
        "greedy_assignments": int(len(alloc)), "greedy_swappable_bdt": swapped,
        "cash_need_coverable_pct": 100 * swapped / cash_need if cash_need else 0.0,
        "efloat_need_coverable_pct": 100 * swapped / ef_need if ef_need else 0.0,
        "median_viable_pair_amount_bdt": float(viable["amount"].median()) if len(viable) else None,
        "median_greedy_assignment_bdt": float(alloc["amount"].median()) if len(alloc) else None,
        "median_distance_km": float(viable["distance_km"].median()) if len(viable) else None,
        "p90_distance_km": float(viable["distance_km"].quantile(0.9)) if len(viable) else None,
        "useful_districts": int(sum(1 for d in by_district.values() if d["viable_pairs"] >= USEFUL_DISTRICT_MIN_PAIRS)),
        "by_district": by_district,
        "_pairs": viable, "_alloc": alloc,
    }


def bar_check(res: dict) -> dict:
    checks = {
        "distinct_agents": res["distinct_agents"]["total"] >= BAR["min_distinct_agents"],
        "viable_pairs": res["viable_pairs"] >= BAR["min_viable_pairs"],
        "cash_side_share": res["cash_side_share_with_counterparty"] >= BAR["min_cash_side_share_with_counterparty"],
        "efloat_side_share": res["efloat_side_share_with_counterparty"] >= BAR["min_efloat_side_share_with_counterparty"],
    }
    return {"checks": checks, "passes": bool(all(checks.values()))}


def representativeness(per_seed: dict, ref_seed: int = 2026) -> dict:
    """Pre-registered rule: typical if every key metric is within the other seeds' [min, max]."""
    others = [s for s in per_seed if s != ref_seed]
    out, above, below = {}, 0, 0
    for k in KEY_METRICS:
        v = per_seed[ref_seed][k]
        vals = [per_seed[s][k] for s in others]
        lo, hi = min(vals), max(vals)
        pos = "within" if lo <= v <= hi else ("above" if v > hi else "below")
        above += pos == "above"
        below += pos == "below"
        rank = 1 + sum(per_seed[s][k] > v for s in per_seed if s != ref_seed)
        out[k] = {"seed_value": v, "others_min": lo, "others_max": hi, "position": pos, "rank_of_5_desc": rank}
    verdict = ("unusually strong" if above > len(KEY_METRICS) / 2 else
               "unusually weak" if below > len(KEY_METRICS) / 2 else
               "typical" if above == below == 0 else "mixed")
    return {"metrics": out, "verdict": verdict}
