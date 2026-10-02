"""Phase 2E: full-operating-day dual-liquidity forecasting for the 08:00 Morning Liquidity Plan.

Pre-registered in docs/FULL_DAY_ML_PROTOCOL.md (research only). One row per agent-day:
features use only completed prior days (<= d-1, known before the 07:00 information cutoff);
targets are the requested-flow peak cash / e-float requirements over the operating window
08:00-23:59 of day d. Models: four HistGradientBoostingRegressor models with the legacy settings.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import config, forecast, ml_attribution as ma
from .data_gen import is_salary_period
from .features import _encode_static

# ---------------------------------------------------------------- pre-registered constants
DEV_SEEDS = (2026, 2027, 2028, 2029, 2030)
CONFIRMATORY_SEEDS = (2031, 2032, 2033, 2034, 2035)
INFO_CUTOFF_HOUR = 7
ALLOCATION_HOUR = 8
OPERATING_HOURS = tuple(range(8, 24))
HISTORY_DAYS = 7
DEV_VALIDATION_START = pd.Timestamp("2026-08-04")
TEST_START = config.TEST_START
COVERAGE_RANGE = (0.85, 0.95)
BROKEN_COVERAGE_RANGE = (0.70, 0.99)

STATIC = ["district_code", "location_cluster_code", "agent_type_code", "agent_volume_segment_code", "market_day"]
CALENDAR = ["day_of_week", "is_weekend", "day_of_month", "is_salary_period", "is_market_day"]
RECENT = ["prev_cash_out", "prev_cash_in", "prev_cash_req", "prev_efloat_req"]
ROLLING = ["cash_out_mean3", "cash_out_mean7", "cash_in_mean3", "cash_in_mean7", "cash_req_mean7", "cash_req_max7",
           "efloat_req_mean7", "efloat_req_max7", "cash_req_std7", "efloat_req_std7"]
SAME_WEEKDAY = ["cash_req_lag7", "efloat_req_lag7", "cash_req_sw_mean", "efloat_req_sw_mean"]
TREND = ["cash_out_trend", "cash_in_trend"]
FEATURES = STATIC + CALENDAR + RECENT + ROLLING + SAME_WEEKDAY + TREND

TARGETS = {"cash": "full_day_cash_requirement", "efloat": "full_day_efloat_requirement"}
MODEL_SPECS = {
    "full_day_cash_requirement_p50": {"target": TARGETS["cash"], "loss": "squared_error", "quantile": None},
    "full_day_cash_requirement_p90": {"target": TARGETS["cash"], "loss": "quantile", "quantile": 0.9},
    "full_day_efloat_requirement_p50": {"target": TARGETS["efloat"], "loss": "squared_error", "quantile": None},
    "full_day_efloat_requirement_p90": {"target": TARGETS["efloat"], "loss": "quantile", "quantile": 0.9},
}
BASELINES = {  # forecast baselines (signal columns), per resource
    "yesterday_requirement": {"cash": "prev_cash_req", "efloat": "prev_efloat_req"},
    "seasonal_requirement_7d": {"cash": "cash_req_mean7", "efloat": "efloat_req_mean7"},
    "seasonal_same_weekday": {"cash": "cash_req_lag7", "efloat": "efloat_req_lag7"},
}
COMPARATOR = "seasonal_requirement_7d"
ML_POLICY = "full_day_ml_p90"
POLICIES = ("status_quo",) + tuple(BASELINES) + (ML_POLICY,)
ORACLE_POLICY = "oracle_full_day"


# ---------------------------------------------------------------- daily arrays and table
def daily_arrays(hourly: pd.DataFrame, agent_ids: list[str]) -> dict:
    """(days x agents) arrays over the operating window 08:00-23:59 of each calendar day."""
    piv = lambda c: hourly.pivot(index="timestamp", columns="agent_id", values=c)[agent_ids].sort_index()  # noqa: E731
    out, inn = piv("requested_cash_out"), piv("requested_cash_in")
    ts = out.index
    assert len(ts) % 24 == 0 and ts[0].hour == 0, "hourly data must cover whole days"
    n_days, n_a = len(ts) // 24, out.shape[1]
    o = out.to_numpy().reshape(n_days, 24, n_a)[:, list(OPERATING_HOURS), :]
    i = inn.to_numpy().reshape(n_days, 24, n_a)[:, list(OPERATING_HOURS), :]
    net = np.cumsum(o - i, axis=1)
    return {"dates": pd.DatetimeIndex(ts[::24]).normalize(),
            "cash_req": np.maximum(net.max(axis=1), 0.0), "efloat_req": np.maximum((-net).max(axis=1), 0.0),
            "cash_out": o.sum(axis=1), "cash_in": i.sum(axis=1)}


def _roll(a: np.ndarray, k: int, n: int, fn) -> np.ndarray:
    return fn(a[k - n:k], axis=0)


def build_daily(hourly: pd.DataFrame, agents: pd.DataFrame) -> pd.DataFrame:
    """One row per agent-day (days with >= 7 complete prior days). Features use days <= d-1 only."""
    ag = _encode_static(agents.sort_values("agent_id").reset_index(drop=True))
    ids = list(ag["agent_id"])
    A = daily_arrays(hourly, ids)
    rows = []
    for k in range(HISTORY_DAYS, len(A["dates"])):
        d = A["dates"][k]
        f = {"date": np.repeat(d, len(ids)), "agent_id": ids}
        for c in STATIC:
            f[c] = ag[c].to_numpy()
        dow = d.dayofweek
        f["day_of_week"] = np.full(len(ids), dow)
        f["is_weekend"] = np.full(len(ids), int(dow in (4, 5)))
        f["day_of_month"] = np.full(len(ids), d.day)
        f["is_salary_period"] = np.full(len(ids), int(is_salary_period(np.array([d.day]))[0]))
        f["is_market_day"] = (ag["market_day"].to_numpy() == dow).astype(int)
        f["prev_cash_out"], f["prev_cash_in"] = A["cash_out"][k - 1], A["cash_in"][k - 1]
        f["prev_cash_req"], f["prev_efloat_req"] = A["cash_req"][k - 1], A["efloat_req"][k - 1]
        for src, name in (("cash_out", "cash_out"), ("cash_in", "cash_in")):
            f[f"{name}_mean3"] = _roll(A[src], k, 3, np.mean)
            f[f"{name}_mean7"] = _roll(A[src], k, 7, np.mean)
        for src, name in (("cash_req", "cash_req"), ("efloat_req", "efloat_req")):
            f[f"{name}_mean7"] = _roll(A[src], k, 7, np.mean)
            f[f"{name}_max7"] = _roll(A[src], k, 7, np.max)
            f[f"{name}_std7"] = _roll(A[src], k, 7, np.std)
            lag7 = A[src][k - 7]
            lag14 = A[src][k - 14] if k >= 14 else np.full(len(ids), np.nan)
            f[f"{name}_lag7"] = lag7
            f[f"{name}_sw_mean"] = np.nanmean(np.vstack([lag7, lag14]), axis=0)
        for name in ("cash_out", "cash_in"):
            m3, m7 = f[f"{name}_mean3"], f[f"{name}_mean7"]
            f[f"{name}_trend"] = np.divide(m3, m7, out=np.full(len(ids), np.nan), where=m7 > 0)
        f[TARGETS["cash"]], f[TARGETS["efloat"]] = A["cash_req"][k], A["efloat_req"][k]
        rows.append(pd.DataFrame(f))
    df = pd.concat(rows, ignore_index=True)
    return df.merge(ag[["agent_id", "district", "location_cluster", "agent_volume_segment",
                        "target_cash_level", "target_efloat_level"]], on="agent_id", how="left")


# ---------------------------------------------------------------- models
def train(df: pd.DataFrame, max_iter: int = 400) -> dict:
    X = df[FEATURES]
    models = {}
    for name, spec in MODEL_SPECS.items():
        m = forecast._make_model(spec["loss"], spec["quantile"], max_iter, FEATURES)
        m.fit(X, df[spec["target"]].to_numpy())
        models[name] = m
    return models


def predict(models: dict, df: pd.DataFrame) -> pd.DataFrame:
    X = df[FEATURES]
    out = pd.DataFrame(index=df.index)
    for res in ("cash", "efloat"):
        p50 = np.clip(models[f"full_day_{res}_requirement_p50"].predict(X), 0, None)
        p90 = np.clip(models[f"full_day_{res}_requirement_p90"].predict(X), 0, None)
        out[f"pred_{res}_p50"] = p50
        out[f"pred_{res}_p90"] = np.maximum(p90, p50)  # P90 >= P50 >= 0
    return out


# ---------------------------------------------------------------- forecast metrics
def forecast_metrics(df: pd.DataFrame, preds: pd.DataFrame, with_groups: bool = True) -> dict:
    res = {}
    for r in ("cash", "efloat"):
        y = df[TARGETS[r]].to_numpy(float)
        p50, p90 = preds[f"pred_{r}_p50"].to_numpy(), preds[f"pred_{r}_p90"].to_numpy()
        e = {"target": TARGETS[r], "ml_p50": forecast.regression_metrics(y, p50), "baselines": {}}
        for b, cols in BASELINES.items():
            e["baselines"][b] = forecast.regression_metrics(y, df[cols[r]].to_numpy(float))
        best = min(e["baselines"], key=lambda k: e["baselines"][k]["mae"])
        e["best_simple_baseline"] = best
        for key, ref in (("improvement_vs_best_simple", e["baselines"][best]),
                         ("improvement_vs_naive_yesterday", e["baselines"]["yesterday_requirement"])):
            e[key] = {"mae_pct": 100 * (1 - e["ml_p50"]["mae"] / ref["mae"]),
                      "rmse_pct": 100 * (1 - e["ml_p50"]["rmse"] / ref["rmse"])}
        e["p90"] = {"nominal_coverage": 0.9, "empirical_coverage": float(np.mean(y <= p90)),
                    "covered": int(np.sum(y <= p90)), "n": int(len(y)), "mean_interval_width": float(np.mean(p90 - p50))}
        if with_groups:
            e["groups"] = {}
            for g in ("location_cluster", "agent_volume_segment"):
                e["groups"][g] = {}
                for val in sorted(df[g].unique()):
                    m = (df[g] == val).to_numpy()
                    e["groups"][g][str(val)] = {
                        "ml_mae": forecast.regression_metrics(y[m], p50[m])["mae"],
                        "seasonal_7d_mae": forecast.regression_metrics(y[m], df.loc[m, BASELINES[COMPARATOR][r]])["mae"],
                        "p90_coverage": float(np.mean(y[m] <= p90[m])), "n": int(m.sum())}
        res[r] = e
    return res


def plausibility(fm: dict, conserved: bool) -> dict:
    """Pre-registered 'clearly broken' checks for development validation."""
    lo, hi = BROKEN_COVERAGE_RANGE
    cov_ok = all(lo <= fm[r]["p90"]["empirical_coverage"] <= hi for r in ("cash", "efloat"))
    worse_both = all(fm[r]["ml_p50"]["mae"] > fm[r]["baselines"]["yesterday_requirement"]["mae"] for r in ("cash", "efloat"))
    checks = {"p90_coverage_within_70_99": cov_ok, "not_worse_than_naive_on_both": not worse_both,
              "conserved": bool(conserved)}
    return {"checks": checks, "clearly_broken": not all(checks.values())}


# ---------------------------------------------------------------- confirmatory bar
def confirmatory_bar(per_seed: dict, pooled_coverage: dict) -> dict:
    """A-D reuse the Phase 2D rule (vs seasonal_requirement_7d); E: pooled P90 coverage in [85%, 95%]."""
    core = ma.ml_value_bar(per_seed)
    lo, hi = COVERAGE_RANGE
    cov = {r: lo <= pooled_coverage[r] <= hi for r in ("cash", "efloat")}
    checks = {"A_ml_not_worse_in_4_of_5": core["checks"]["ml_not_worse_in_4_of_5"],
              "B_median_incremental_ge_5pct": core["checks"]["median_incremental_ge_5pct"],
              "C_side_worse_gt5pct_in_at_most_1_seed": core["checks"]["side_increase_gt5pct_in_at_most_1_seed"],
              "D_exact_conservation_all": core["checks"]["exact_conservation_all"],
              "E_pooled_p90_coverage_85_95": all(cov.values())}
    return {**{k: v for k, v in core.items() if k not in ("checks", "passes")}, "pooled_p90_coverage": pooled_coverage,
            "checks": checks, "passes": bool(all(checks.values()))}


# ---------------------------------------------------------------- policy signals
def policy_signals(day_rows: pd.DataFrame, preds: pd.DataFrame | None) -> dict:
    """Allocation signals per policy for one day (rows in agent_id order). Oracle kept separate."""
    sig = {b: (day_rows[c["cash"]].to_numpy(float), day_rows[c["efloat"]].to_numpy(float)) for b, c in BASELINES.items()}
    if preds is not None:
        sig[ML_POLICY] = (preds["pred_cash_p90"].to_numpy(), preds["pred_efloat_p90"].to_numpy())
    return sig


def oracle_signal(day_rows: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """ORACLE - evaluation only, impossible operationally: actual full-day requirements."""
    return day_rows[TARGETS["cash"]].to_numpy(float), day_rows[TARGETS["efloat"]].to_numpy(float)


# ---------------------------------------------------------------- held-out / validation replay
def simulate_policies(hourly: pd.DataFrame, agents: pd.DataFrame, daily: pd.DataFrame, preds: pd.DataFrame,
                      days: pd.DatetimeIndex) -> dict:
    """Replay ``days`` under every policy (same budgets, floors, allocator, demand). Returns plans, sims,
    hours, masks, requested matrices and conservation proof. ``daily``/``preds`` hold rows for ``days``."""
    from . import prepositioning as pp
    ag = agents.sort_values("agent_id").reset_index(drop=True)
    ids = list(ag["agent_id"])
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
    names = POLICIES + (ORACLE_POLICY,)
    plans = {k: ({}, {}) for k in names}
    for d in days:
        rows = daily[daily["date"] == d].sort_values("agent_id")
        assert list(rows["agent_id"]) == ids
        sig = policy_signals(rows, preds.loc[rows.index])
        sig[ORACLE_POLICY] = oracle_signal(rows)
        plans["status_quo"][0][d], plans["status_quo"][1][d] = tc, te
        for name, (cs, es) in sig.items():
            ac, ae, _ = ma.allocate(ag, cs, es, "need")
            plans[name][0][d], plans[name][1][d] = ac, ae
    district = ag["district"].to_numpy()
    cons = {}
    for name, (pc, pe) in plans.items():
        ok, mx = True, 0
        for d in days:
            for p, sq in ((pc[d], tc), (pe[d], te)):
                diff = int(pd.Series(p - sq).groupby(district).sum().abs().max())
                mx = max(mx, diff)
                ok &= diff == 0 and bool((p >= 0).all()) and int(p.sum()) == int(sq.sum())
        cons[name] = {"exact": bool(ok), "max_abs_district_diff_bdt": mx}
    sims = {k: pp.replay(ro, ri, hours, c0, e0, pc, pe) for k, (pc, pe) in plans.items()}
    primary = np.asarray(hours.hour >= ALLOCATION_HOUR)
    secondary = np.asarray(hours >= start + pd.Timedelta(hours=ALLOCATION_HOUR))
    return {"ids": ids, "agents": ag, "hours": hours, "ro": ro, "ri": ri, "plans": plans, "sims": sims,
            "primary_mask": primary, "secondary_mask": secondary, "conservation": cons,
            "budgets": {"cash": int(tc.sum()), "efloat": int(te.sum())}, "tc": tc, "te": te, "days": days}


def impact_summary(sim: dict, with_harm: bool = True) -> dict:
    """Service metrics (primary + secondary windows), ML vs comparator, harm and group analysis."""
    from . import prepositioning as pp
    out = {"conservation": sim["conservation"],
           "conserved_all_policies": all(c["exact"] for c in sim["conservation"].values()),
           "network_daily_budget_bdt": sim["budgets"], "policies": {}}
    pm = sim["primary_mask"]
    for k, s in sim["sims"].items():
        out["policies"][k] = {"primary_operating_hours": pp.service_metrics(s, sim["ro"], sim["ri"], pm),
                              "secondary_continuous": pp.service_metrics(s, sim["ro"], sim["ri"], sim["secondary_mask"])}
    prim = {k: v["primary_operating_hours"] for k, v in out["policies"].items()}
    out["oracle_label"] = "ORACLE - evaluation only, impossible operationally"
    out["best_simple_policy"] = min(BASELINES, key=lambda b: prim[b]["combined_unmet_bdt"])
    out["incremental_vs_comparator"] = ma.incremental(prim[ML_POLICY], prim[COMPARATOR])
    out["incremental_vs_best_simple"] = ma.incremental(prim[ML_POLICY], prim[out["best_simple_policy"]])
    if not with_harm:
        return out
    per_agent = {k: (s["unmet_out"][pm] + s["unmet_in"][pm]).sum(axis=0) for k, s in sim["sims"].items()}
    tol = pp.BETTER_WORSE_TOLERANCE_BDT
    ag, ids, days = sim["agents"], sim["ids"], sim["days"]
    harm = {}
    for name in (COMPARATOR, ML_POLICY):
        dlt = per_agent[name] - per_agent["status_quo"]
        worst = [i for i in np.argsort(-dlt)[:5] if dlt[i] > tol]
        groups = {}
        ac = np.sum([sim["plans"][name][0][d] for d in days], axis=0)
        ae = np.sum([sim["plans"][name][1][d] for d in days], axis=0)
        for g in ("location_cluster", "agent_volume_segment"):
            groups[g] = {}
            for val in sorted(ag[g].unique()):
                m = (ag[g] == val).to_numpy()
                s0, s1 = per_agent["status_quo"][m].sum(), per_agent[name][m].sum()
                groups[g][str(val)] = {"cash_ratio": float(ac[m].sum() / (sim["tc"][m].sum() * len(days))),
                                       "efloat_ratio": float(ae[m].sum() / (sim["te"][m].sum() * len(days))),
                                       "combined_unmet_change_pct": -ma.reduction_pct(s1, s0),
                                       "harmed_agents": int((dlt[m] > tol).sum()), "agents": int(m.sum())}
        harm[name] = {"vs_status_quo": {"better": int((dlt < -tol).sum()), "worse": int((dlt > tol).sum()),
                                        "total_benefit_bdt": float(-dlt[dlt < -tol].sum()),
                                        "total_harm_bdt": float(dlt[dlt > tol].sum())},
                      "worst_harmed": [{"agent_id": ids[i], "location_cluster": ag.loc[i, "location_cluster"],
                                        "segment": ag.loc[i, "agent_volume_segment"], "change_bdt": float(dlt[i])} for i in worst],
                      "groups": groups}
    d_ml = per_agent[ML_POLICY] - per_agent[COMPARATOR]
    harm["ml_vs_comparator_agents"] = {"better": int((d_ml < -tol).sum()), "worse": int((d_ml > tol).sum()),
                                       "unchanged": int((np.abs(d_ml) <= tol).sum())}
    out["harm"] = harm
    return out
