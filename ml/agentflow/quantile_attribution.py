"""Phase 2F: cautious non-ML baseline attribution for the frozen full-day ML Morning Liquidity Plan.

Pre-registered in docs/QUANTILE_ATTRIBUTION_PROTOCOL.md (research only). This module only READS the
frozen Phase 2E modules (full_day, forecast, ml_attribution, prepositioning); it never changes the ML
path. History signals use the previous 7 complete operating days (08:00-23:59) only.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import full_day as fd, ml_attribution as ma

# ---------------------------------------------------------------- pre-registered constants
AUDIT_SEEDS = (2036, 2037, 2038, 2039, 2040)
PRIOR_SEEDS = fd.DEV_SEEDS + fd.CONFIRMATORY_SEEDS
REGRESSION_SEED = 2031
FROZEN_SPEC_COMMIT = "3128176e23b4a5a2dde883e8dff8a75f21e35540"
FROZEN_SHA256 = {
    "ml/agentflow/full_day.py": "0df1ff8ed3230974206e3dae410aa659bc5030fce464aa1580202f14f6bebfd1",
    "ml/agentflow/forecast.py": "5f21624188a0c15a1c9137cffe0477ddb9713296b3aa9082600aade5c4c4c956",
    "ml/agentflow/ml_attribution.py": "61138bfb50448de0b3cf52ffe787ff1a8430f6329fd6d1a016b8ba8c7d4c0cfa",
    "ml/agentflow/prepositioning.py": "2c2b14164103e689fb898cae19c4c9da06da0828cff965982afe50041046aab9",
    "ml/agentflow/dual_world.py": "eec1f1555192e7e3ada503eb6758d6ef7bb10b621c773b5f63b2e2df3eb63eb8",
    "ml/agentflow/features.py": "8887461a5dbaf69112ccbd403a9172ad0beba0ba0421684fda4e2d74bc498b11",
    "ml/agentflow/data_gen.py": "9c3da9a83dbd45538e819aa668e0ee9d5c49e96490c28b4281e6998bc194e19f",
}
QUANTILE = 0.90
HISTORY_DAYS = 7
MEAN7, Q90, MAX7 = "seasonal_requirement_mean7", "seasonal_requirement_q90_7d", "seasonal_requirement_max7"
ML = "frozen_full_day_ml_p90"
YESTERDAY, ORACLE = "yesterday_requirement", "oracle_full_day"
CAUTIOUS = (Q90, MAX7)
POLICIES = ("status_quo", MEAN7, Q90, MAX7, ML, YESTERDAY)
BAR = {"min_seeds_ml_le_q90": 4, "min_seeds_ml_le_max7": 4, "min_median_incremental_pct": 5.0,
       "max_side_worse_pct": 5.0, "max_seeds_side_worse": 1}


# ---------------------------------------------------------------- history signals
def q90_linear(x: np.ndarray, axis: int = 0) -> np.ndarray:
    """Empirical 90th percentile by linear interpolation (== numpy.quantile(..., method="linear")).

    For n values sorted ascending, h = (n - 1) * 0.9, q = x[floor(h)] + (h - floor(h)) * (x[floor(h)+1] - x[floor(h)]).
    """
    s = np.sort(np.asarray(x, float), axis=axis)
    n = s.shape[axis]
    h = (n - 1) * QUANTILE
    lo = int(np.floor(h))
    hi = min(lo + 1, n - 1)
    a, b = np.take(s, lo, axis=axis), np.take(s, hi, axis=axis)
    return a + (h - lo) * (b - a)


def history_signals(A: dict, k: int) -> dict:
    """Signals for day index k from the previous 7 complete operating days (k-7 .. k-1) of daily_arrays A."""
    if k < HISTORY_DAYS:
        raise ValueError("needs 7 complete prior operating days")
    out = {}
    for r, key in (("cash", "cash_req"), ("efloat", "efloat_req")):
        w = A[key][k - HISTORY_DAYS:k]
        out[r] = {MEAN7: w.mean(axis=0), Q90: q90_linear(w, axis=0), MAX7: w.max(axis=0), YESTERDAY: A[key][k - 1]}
    return out


# ---------------------------------------------------------------- simulation (same allocator for all)
def simulate(hourly: pd.DataFrame, agents: pd.DataFrame, daily: pd.DataFrame, preds: pd.DataFrame,
             days: pd.DatetimeIndex) -> dict:
    """Replay ``days`` for every policy with identical budgets, floors, allocator and requested flows."""
    from . import prepositioning as pp
    ag = agents.sort_values("agent_id").reset_index(drop=True)
    ids = list(ag["agent_id"])
    A = fd.daily_arrays(hourly, ids)
    piv = lambda c: hourly.pivot(index="timestamp", columns="agent_id", values=c)[ids].sort_index()  # noqa: E731
    ro_all, ri_all = piv("requested_cash_out"), piv("requested_cash_in")
    cb, eb = piv("cash_balance"), piv("efloat_balance")
    start, end = days[0], days[-1] + pd.Timedelta(hours=23)
    win = (ro_all.index >= start) & (ro_all.index <= end)
    hours = ro_all.index[win]
    ro, ri = ro_all.to_numpy()[win], ri_all.to_numpy()[win]
    prev = ro_all.index.get_loc(start - pd.Timedelta(hours=1))
    c0, e0 = cb.to_numpy()[prev], eb.to_numpy()[prev]
    tc = ag["target_cash_level"].round().astype(np.int64).to_numpy()
    te = ag["target_efloat_level"].round().astype(np.int64).to_numpy()
    names = POLICIES + (ORACLE,)
    plans = {k: ({}, {}) for k in names}
    hist_cov = {s: {"cash": [0, 0], "efloat": [0, 0]} for s in (MEAN7, Q90, MAX7, YESTERDAY)}
    for d in days:
        k = int(np.where(A["dates"] == d)[0][0])
        hs = history_signals(A, k)
        rows = daily[daily["date"] == d].sort_values("agent_id")
        assert list(rows["agent_id"]) == ids
        p = preds.loc[rows.index]
        sig = {s: (hs["cash"][s], hs["efloat"][s]) for s in (MEAN7, Q90, MAX7, YESTERDAY)}
        sig[ML] = (p["pred_cash_p90"].to_numpy(), p["pred_efloat_p90"].to_numpy())
        sig[ORACLE] = fd.oracle_signal(rows)  # ORACLE - evaluation only
        actual = {"cash": rows[fd.TARGETS["cash"]].to_numpy(), "efloat": rows[fd.TARGETS["efloat"]].to_numpy()}
        for s in hist_cov:
            for r, i in (("cash", 0), ("efloat", 1)):
                hist_cov[s][r][0] += int(np.sum(actual[r] <= sig[s][i]))
                hist_cov[s][r][1] += len(ids)
        plans["status_quo"][0][d], plans["status_quo"][1][d] = tc, te
        for name, (cs, es) in sig.items():
            ac, ae, _ = ma.allocate(ag, cs, es, "need")
            plans[name][0][d], plans[name][1][d] = ac, ae
    district = ag["district"].to_numpy()
    cons = {}
    for name, (pc, pe) in plans.items():
        ok, mx = True, 0
        for d in days:
            for p_, sq in ((pc[d], tc), (pe[d], te)):
                diff = int(pd.Series(p_ - sq).groupby(district).sum().abs().max())
                mx = max(mx, diff)
                ok &= diff == 0 and bool((p_ >= 0).all()) and int(p_.sum()) == int(sq.sum())
        cons[name] = {"exact": bool(ok), "max_abs_district_diff_bdt": mx}
    sims = {k: pp.replay(ro, ri, hours, c0, e0, pc, pe) for k, (pc, pe) in plans.items()}
    return {"ids": ids, "agents": ag, "hours": hours, "ro": ro, "ri": ri, "plans": plans, "sims": sims,
            "primary_mask": np.asarray(hours.hour >= fd.ALLOCATION_HOUR),
            "secondary_mask": np.asarray(hours >= start + pd.Timedelta(hours=fd.ALLOCATION_HOUR)),
            "conservation": cons, "budgets": {"cash": int(tc.sum()), "efloat": int(te.sum())},
            "tc": tc, "te": te, "days": days,
            "historical_signal_coverage": {s: {r: v[0] / v[1] for r, v in c.items()} for s, c in hist_cov.items()}}


def best_cautious(prim: dict) -> str:
    """Lower primary combined unmet among q90_7d and max7 (ties -> q90_7d)."""
    return min(CAUTIOUS, key=lambda k: (prim[k]["combined_unmet_bdt"], CAUTIOUS.index(k)))


def attribution_bar(per_seed: dict) -> dict:
    """Pre-registered A-E rule. per_seed[s] needs: prim (policy -> metrics), incremental, conserved_all_policies."""
    le_q90 = sum(r["prim"][ML]["combined_unmet_bdt"] <= r["prim"][Q90]["combined_unmet_bdt"] for r in per_seed.values())
    le_max = sum(r["prim"][ML]["combined_unmet_bdt"] <= r["prim"][MAX7]["combined_unmet_bdt"] for r in per_seed.values())
    inc = [r["incremental"] for r in per_seed.values()]
    med = float(np.median([i["combined_unmet_reduction_pct"] for i in inc]))
    side = sum((i["cash_unmet_reduction_pct"] < -BAR["max_side_worse_pct"]) or
               (i["efloat_unmet_reduction_pct"] < -BAR["max_side_worse_pct"]) for i in inc)
    cons = all(r["conserved_all_policies"] for r in per_seed.values())
    checks = {"A_ml_le_q90_in_4_of_5": le_q90 >= BAR["min_seeds_ml_le_q90"],
              "B_ml_le_max7_in_4_of_5": le_max >= BAR["min_seeds_ml_le_max7"],
              "C_median_incremental_vs_best_cautious_ge_5pct": med >= BAR["min_median_incremental_pct"],
              "D_side_worse_gt5pct_in_at_most_1_seed": side <= BAR["max_seeds_side_worse"],
              "E_exact_conservation_all": cons}
    return {"seeds_ml_le_q90": int(le_q90), "seeds_ml_le_max7": int(le_max),
            "median_incremental_vs_best_cautious_pct": med, "seeds_side_worse_gt5pct": int(side),
            "checks": checks, "passes": bool(all(checks.values()))}


def harm_groups(sim: dict, names=(ML,), ref: str = "status_quo") -> dict:
    """Per-policy benefit/harm vs ``ref``, worst-harmed agents and group shifts (primary window)."""
    from . import prepositioning as pp
    pm, ag, ids, days = sim["primary_mask"], sim["agents"], sim["ids"], sim["days"]
    per_agent = {k: (s["unmet_out"][pm] + s["unmet_in"][pm]).sum(axis=0) for k, s in sim["sims"].items()}
    tol = pp.BETTER_WORSE_TOLERANCE_BDT
    uph = ((ag["location_cluster"] == "urban_periphery") & (ag["agent_volume_segment"] == "high")).to_numpy()
    out = {}
    for name in names:
        dlt = per_agent[name] - per_agent[ref]
        ac = np.sum([sim["plans"][name][0][d] for d in days], axis=0)
        ae = np.sum([sim["plans"][name][1][d] for d in days], axis=0)
        groups = {}
        for g in ("location_cluster", "agent_volume_segment"):
            groups[g] = {}
            for val in sorted(ag[g].unique()):
                m = (ag[g] == val).to_numpy()
                s0, s1 = per_agent[ref][m].sum(), per_agent[name][m].sum()
                groups[g][str(val)] = {"cash_ratio": float(ac[m].sum() / (sim["tc"][m].sum() * len(days))),
                                       "efloat_ratio": float(ae[m].sum() / (sim["te"][m].sum() * len(days))),
                                       "combined_unmet_change_pct": -ma.reduction_pct(s1, s0),
                                       "harmed_agents": int((dlt[m] > tol).sum()), "agents": int(m.sum())}
        worst = [i for i in np.argsort(-dlt)[:5] if dlt[i] > tol]
        out[name] = {"better": int((dlt < -tol).sum()), "worse": int((dlt > tol).sum()),
                     "unchanged": int((np.abs(dlt) <= tol).sum()),
                     "total_benefit_bdt": float(-dlt[dlt < -tol].sum()), "total_harm_bdt": float(dlt[dlt > tol].sum()),
                     "worst_harmed": [{"agent_id": ids[i], "location_cluster": ag.loc[i, "location_cluster"],
                                       "segment": ag.loc[i, "agent_volume_segment"], "change_bdt": float(dlt[i])} for i in worst],
                     "groups": groups,
                     "urban_periphery_high_volume": {"agents": int(uph.sum()), "harmed": int((dlt[uph] > tol).sum()),
                                                     "change_pct": -ma.reduction_pct(per_agent[name][uph].sum(), per_agent[ref][uph].sum())}}
    return out
