"""Evaluation of the Dual-Liquidity Synthetic World v2 (pre-registered protocol, docs/DUAL_WORLD_V2.md §5).

Everything here reads and writes the dual-world paths only. Label on every artifact:
"Synthetic held-out simulation - Dual-Liquidity World v2".
"""
from __future__ import annotations

import time

import numpy as np
import pandas as pd

from . import config, dual, dual_world as dw, features, forecast, risk
from .engine import OPERATING_HOURS, training_shortage_rate
from .features import EFLOAT_TARGET, TARGETS, _future_window_sum

LABEL = "Synthetic held-out simulation - Dual-Liquidity World v2"
H = config.HORIZON_H
DEFAULT_AS_OF = pd.Timestamp("2026-08-31 13:00")
VALIDITY_BAR = {"min_prevalence": 0.01, "min_positive_rows": 100, "min_agents": 20}


def _r(x, nd=4):
    if isinstance(x, dict):
        return {k: _r(v, nd) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_r(v, nd) for v in x]
    if isinstance(x, (float, np.floating)):
        return round(float(x), nd)
    if isinstance(x, np.integer):
        return int(x)
    return x


def build(world: dw.DualWorld) -> pd.DataFrame:
    f = features.build_features(world.hourly, world.agents)
    gid = f["agent_id"]
    f["unmet_in_next_6h"] = _future_window_sum(f["unmet_cash_in"].groupby(gid))
    f["unmet_out_next_6h"] = f["unmet_next_6h"]
    return f


def _binary(y: np.ndarray, alert: np.ndarray) -> dict:
    y, alert = np.asarray(y, bool), np.asarray(alert, bool)
    tp, fp, fn = int((alert & y).sum()), int((alert & ~y).sum()), int((~alert & y).sum())
    p, r = tp / max(tp + fp, 1), tp / max(tp + fn, 1)
    return {"positives": int(y.sum()), "prevalence": float(y.mean()), "alerts": int(alert.sum()),
            "alert_rate": float(alert.mean()), "true_positives": tp, "false_positives": fp, "missed": fn,
            "precision": p, "recall": r, "f1": 2 * p * r / max(p + r, 1e-9)}


def _cash_entry(test_df: pd.DataFrame, preds: pd.DataFrame) -> dict:
    y = test_df["future_6h_net_cash_demand"].to_numpy(float)
    e = {"target": "future_6h_net_cash_demand",
         "ml_model": forecast.regression_metrics(y, preds["pred_net_requirement_6h"]), "baselines": {}}
    for b, col in forecast.BASELINES["net_requirement"].items():
        e["baselines"][b] = forecast.regression_metrics(y, test_df[col].to_numpy(float))
    best = min(e["baselines"], key=lambda k: e["baselines"][k]["mae"])
    e["best_baseline"] = best
    for key, ref in (("improvement_vs_best_baseline", e["baselines"][best]),
                     ("improvement_vs_naive", e["baselines"]["naive_yesterday"])):
        e[key] = {"mae_pct": 100 * (1 - e["ml_model"]["mae"] / ref["mae"]),
                  "rmse_pct": 100 * (1 - e["ml_model"]["rmse"] / ref["rmse"])}
    p50, p90 = preds["pred_net_requirement_6h"].to_numpy(), preds["pred_net_requirement_p90_6h"].to_numpy()
    e["quantile_p90"] = {"nominal_coverage": 0.9, "empirical_coverage": float(np.mean(y <= p90)),
                         "mean_band_width": float(np.mean(p90 - p50))}
    groups = {}
    for gcol in ("location_cluster", "agent_volume_segment"):
        groups[gcol] = {}
        for g in sorted(test_df[gcol].unique()):
            m = (test_df[gcol] == g).to_numpy()
            ml = forecast.regression_metrics(y[m], p50[m])
            groups[gcol][str(g)] = {"ml_mae": ml["mae"], "ml_wape": ml["wape"],
                                    "naive_mae": forecast.regression_metrics(y[m], test_df.loc[m, "net_req_same_window_1d"])["mae"],
                                    "seasonal_mae": forecast.regression_metrics(y[m], test_df.loc[m, "net_req_same_window_avg7"])["mae"],
                                    "p90_coverage": float(np.mean(y[m] <= p90[m])), "n": ml["n"]}
    e["group_consistency"] = groups
    return e


def forecast_block(df: pd.DataFrame, preds: pd.DataFrame, with_groups: bool = True) -> dict:
    p = preds.reindex(df.index)
    cash = _cash_entry(df, p)
    ef = dual.efloat_forecast_metrics(df, p["pred_efloat_requirement_6h"].to_numpy(),
                                      p["pred_efloat_requirement_p90_6h"].to_numpy())
    if not with_groups:
        cash.pop("group_consistency")
        ef.pop("group_consistency")
    return {"cash_requirement": cash, "efloat_requirement": ef}


def pressure_block(d: pd.DataFrame, p: pd.DataFrame, hist_rate: pd.Series) -> dict:
    """Pressure prevalence and early-warning quality at decision rows ``d`` (pre-registered definitions)."""
    cb, eb = d["cash_balance"].to_numpy(float), d["efloat_balance"].to_numpy(float)
    c50, c90 = p["pred_net_requirement_6h"].to_numpy(), p["pred_net_requirement_p90_6h"].to_numpy()
    e50, e90 = p["pred_efloat_requirement_6h"].to_numpy(), p["pred_efloat_requirement_p90_6h"].to_numpy()
    sides = {
        "cash": {"forecast_pressure": cb < c50, "forecast_watch_p90": cb < c90,
                 "requirement_label": cb < d["future_6h_net_cash_demand"].to_numpy(float),
                 "realised_current_hour": d["unmet_cash_out"].to_numpy(float) > 0,
                 "realised_next_6h": d["unmet_out_next_6h"].to_numpy(float) > 0},
        "efloat": {"forecast_pressure": eb < e50, "forecast_watch_p90": eb < e90,
                   "requirement_label": eb < d["future_6h_net_efloat_demand"].to_numpy(float),
                   "realised_current_hour": d["unmet_cash_in"].to_numpy(float) > 0,
                   "realised_next_6h": d["unmet_in_next_6h"].to_numpy(float) > 0},
    }
    sides["dual"] = {k: sides["cash"][k] & sides["efloat"][k] for k in sides["cash"]}
    agents = d["agent_id"].to_numpy()
    out = {"n_decisions": int(len(d)), "rows": "held-out operating hours 08:00-21:00", "prevalence": {}, "early_warning": {}}
    for side, s in sides.items():
        out["prevalence"][side] = {k: {"rate": float(v.mean()), "rows": int(v.sum()),
                                       "agents": int(len(np.unique(agents[v])))} for k, v in s.items()}
        out["early_warning"][side] = {
            "forecast_pressure_vs_realised_next_6h": _binary(s["realised_next_6h"], s["forecast_pressure"]),
            "forecast_watch_p90_vs_realised_next_6h": _binary(s["realised_next_6h"], s["forecast_watch_p90"]),
            "forecast_pressure_vs_requirement_label": _binary(s["requirement_label"], s["forecast_pressure"]),
        }
    cash_st = dw.resource_status(cb, c50, c90)
    ef_st = dw.resource_status(eb, e50, e90)
    state = dw.liquidity_state_matrix(cash_st, ef_st)
    out["liquidity_state_share"] = {k: float(np.mean(state == k)) for k in dw.LIQUIDITY_STATES}
    r = risk.compute_risk(cb, c50, c90, d["velocity_ratio_3h"].to_numpy(), d["agent_id"].map(hist_rate).fillna(0).to_numpy())
    lvl = r["risk_level"].to_numpy()
    out["legacy_cash_risk_level_by_state"] = {
        k: {lv: int(((state == k) & (lvl == lv)).sum()) for lv in ("LOW", "MEDIUM", "HIGH", "CRITICAL")}
        for k in dw.LIQUIDITY_STATES}
    out["_state"] = state
    return out


def service_block(h: pd.DataFrame) -> dict:
    """Status-quo service metrics over the rows of ``h`` (agent-hours)."""
    ro, so, uo = h["requested_cash_out"].sum(), h["served_cash_out"].sum(), h["unmet_cash_out"].sum()
    ri, si, ui = h["requested_cash_in"].sum(), h["served_cash_in"].sum(), h["unmet_cash_in"].sum()
    ce, ee = h["unmet_cash_out"] > 0, h["unmet_cash_in"] > 0
    by_agent = pd.DataFrame({"c": ce, "e": ee, "a": h["agent_id"]}).groupby("a")[["c", "e"]].any()
    return {
        "agent_hours": int(len(h)),
        "cash_side": {"shortage_events": int(ce.sum()), "unmet_cash_out_bdt": float(uo),
                      "requested_cash_out_bdt": float(ro), "cash_out_fill_rate": float(so / max(ro, 1))},
        "efloat_side": {"shortage_events": int(ee.sum()), "unmet_cash_in_bdt": float(ui),
                        "requested_cash_in_bdt": float(ri), "cash_in_fill_rate": float(si / max(ri, 1))},
        "network": {"dual_shortage_agent_hours": int((ce & ee).sum()),
                    "agent_hours_fully_serviceable_both_sides": int((~ce & ~ee).sum()),
                    "share_agent_hours_fully_serviceable": float((~ce & ~ee).mean()),
                    "agents_with_cash_shortage": int(by_agent["c"].sum()),
                    "agents_with_efloat_shortage": int(by_agent["e"].sum()),
                    "agents_with_both_types": int((by_agent["c"] & by_agent["e"]).sum()),
                    "total_requested_bdt": float(ro + ri), "total_served_bdt": float(so + si),
                    "combined_value_fill_rate": float((so + si) / max(ro + ri, 1))},
    }


def validity(pressure: dict) -> dict:
    res = {"bar": VALIDITY_BAR, "basis": "realised next-6h unmet events at held-out decision times", "sides": {}}
    for side in ("cash", "efloat"):
        v = pressure["prevalence"][side]["realised_next_6h"]
        ok = (v["rate"] >= VALIDITY_BAR["min_prevalence"] and v["rows"] >= VALIDITY_BAR["min_positive_rows"]
              and v["agents"] >= VALIDITY_BAR["min_agents"])
        res["sides"][side] = {**v, "passes": bool(ok)}
    res["passes"] = all(s["passes"] for s in res["sides"].values())
    return res


def world_hash(world: dw.DualWorld) -> str:
    import hashlib
    hv = pd.util.hash_pandas_object(world.hourly, index=False).to_numpy()
    av = pd.util.hash_pandas_object(world.agents, index=False).to_numpy()
    return hashlib.sha256(hv.tobytes() + av.tobytes()).hexdigest()


def run(world: dw.DualWorld, max_iter: int = 400, model_path=dw.MODEL_PATH) -> dict:
    f = build(world)
    train_df, test_df = features.time_split(f)
    has_hist = f["out_same_window_avg7"].notna() & f["out_rolling_mean_168h"].notna()
    has_target = f[TARGETS + [EFLOAT_TARGET]].notna().all(axis=1)
    dev = f[has_hist & has_target & (f["timestamp"] < dw.VALIDATION_START - pd.Timedelta(hours=H))]
    val = f[has_hist & has_target & (f["timestamp"] >= dw.VALIDATION_START)
            & (f["timestamp"] + pd.Timedelta(hours=H) < dw.TEST_START)]
    assert val["timestamp"].max() + pd.Timedelta(hours=H) < dw.TEST_START
    assert dev["timestamp"].max() + pd.Timedelta(hours=H) < dw.VALIDATION_START

    t0 = time.time()
    b_val = forecast.train(dev, max_iter=max_iter)
    validation = {"dev_start": str(dev["timestamp"].min()), "dev_end": str(dev["timestamp"].max()),
                  "val_start": str(val["timestamp"].min()), "val_end": str(val["timestamp"].max()),
                  "dev_rows": int(len(dev)), "val_rows": int(len(val)),
                  **forecast_block(val, b_val.predict(val), with_groups=False), "used_for_selection": False}
    fit_val = round(time.time() - t0, 1)

    bundle = forecast.train(train_df, max_iter=max_iter)
    bundle.metadata["world_version"] = dw.WORLD_VERSION
    bundle.save(model_path)
    preds = bundle.predict(test_df)
    held_out = {"test_start": str(test_df["timestamp"].min()), "test_end": str(test_df["timestamp"].max()),
                "n_test_rows": int(len(test_df)), **forecast_block(test_df, preds)}

    hist_rate = training_shortage_rate(f)
    d = test_df[test_df["hour"].isin(OPERATING_HOURS)]
    pressure = pressure_block(d, preds.loc[d.index], hist_rate)
    state = pressure.pop("_state")
    snap = d["timestamp"] == DEFAULT_AS_OF
    default_counts = {k: int((state[snap.to_numpy()] == k).sum()) for k in dw.LIQUIDITY_STATES}

    h = world.hourly
    test_h = h[h["timestamp"] >= dw.TEST_START]
    train_h = h[h["timestamp"] < dw.TEST_START]
    boundaries = {"train": [str(h["timestamp"].min()), str(train_df["timestamp"].max())],
                  "purge_hours": H, "validation_fit_end": validation["dev_end"],
                  "validation": [validation["val_start"], validation["val_end"]],
                  "test": [held_out["test_start"], held_out["test_end"]]}
    common = {"label": LABEL, "world_version": dw.WORLD_VERSION, "assumptions_version": dw.ASSUMPTIONS_VERSION,
              "seed": dw.SEED}
    a = world.agents
    summary = {**common, "world_hash": world_hash(world), "assumptions": dw.ASSUMPTIONS, "boundaries": boundaries,
               "n_agents": int(len(a)), "n_rows": int(len(h)),
               "agents_by_cluster": a["location_cluster"].value_counts().sort_index().to_dict(),
               "median_cash_in_ratio_by_cluster": a.groupby("location_cluster")["cash_in_ratio"].median().to_dict(),
               "median_target_cash_by_cluster": a.groupby("location_cluster")["target_cash_level"].median().to_dict(),
               "median_target_efloat_by_cluster": a.groupby("location_cluster")["target_efloat_level"].median().to_dict(),
               "flow_event_agent_hours": h["flow_event"].value_counts().to_dict(),
               "anomaly_agent_hours": int(h["known_anomaly_label"].sum()),
               "training_period_service": service_block(train_h)}
    fm = {**common, "boundaries": boundaries, "model_specs": {**forecast.MODEL_SPECS, **forecast.EFLOAT_MODEL_SPECS},
          "algorithm": "sklearn.ensemble.HistGradientBoostingRegressor (legacy settings, unchanged)",
          "selection_protocol": "fixed pre-registered models; validation slice recorded only; test evaluated once",
          "validation": validation, "held_out": held_out}
    sq = {**common, "boundaries": boundaries, "held_out_service": service_block(test_h),
          "held_out_decision_time_pressure": pressure,
          "default_decision_time": {"as_of": str(DEFAULT_AS_OF), "liquidity_state_counts": default_counts},
          "validity_for_phase_2b": validity(pressure)}
    meta = {**common, **{k: v for k, v in bundle.metadata.items() if k != "model_specs"},
            "features_cash": bundle.features, "features_efloat": bundle.efloat_features,
            "validation_fit_seconds": fit_val}
    return {"world_summary.json": _r(summary), "forecast_metrics.json": _r(fm),
            "status_quo_impact.json": _r(sq), "training_metadata.json": _r(meta)}
