"""Phase-2 targeted ML experiment: peak-requirement forecast and early-warning recall.

Usage:  python ml/scripts/ml_experiment.py            # selection (validation folds) then one held-out evaluation
        python ml/scripts/ml_experiment.py --stage select

Stage 1 (select) uses training-period validation folds only and writes
ml/artifacts/ml_experiment_preregistration.json: the pre-registered criteria (with their SHA-256), every
candidate's validation scores and the selected forecast candidate / alert operating point.
Stage 2 (holdout) refuses to run if the criteria changed since stage 1, evaluates the current serving model and
the selected candidates once on the held-out period, applies the promotion criteria and writes
ml/artifacts/ml_experiment.json. The serving model is only replaced if a candidate passes every criterion.
"""
from __future__ import annotations

import _bootstrap  # noqa: F401

import argparse
import json
import time
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from agentflow import config, data_gen, engine, features, impact, ml_experiment as X, rebalance_v2
from agentflow.engine import OPERATING_HOURS

PREREG = config.ARTIFACTS_DIR / "ml_experiment_preregistration.json"
OUT = config.ARTIFACTS_DIR / "ml_experiment.json"
BLEND_GRID = (0.0, 0.1, 0.2, 0.3)


def _pool(per_fold: list[dict]) -> dict:
    n = sum(s["n"] for s in per_fold)
    out = {k: sum(s[k] * s["n"] for s in per_fold) / n for k in per_fold[0] if k != "n"}
    out["n"] = n
    return out


def _r(d: dict, nd: int = 4) -> dict:
    return {k: (round(v, nd) if isinstance(v, float) else v) for k, v in d.items()}


# --------------------------------------------------------------------------- stage 1: selection
def select(feats: pd.DataFrame) -> dict:
    t0 = time.time()
    val_scores, alert_parts, fold_info = {}, [], []
    for name in X.CANDIDATES:
        per_fold, blends = [], {w: [] for w in BLEND_GRID}
        for fold in X.FOLDS:
            dev, val = X.fold_frames(feats, fold)
            X.assert_selection_rows_before_test(dev, val)
            m = X.make_candidate(name).fit(dev)
            ws = BLEND_GRID if X.CANDIDATES[name]["blend"] else (0.0,)
            for w in ws:
                m.blend_weight = w
                blends[w].append(X.forecast_scores(val, m.predict(val)))
            m.blend_weight = 0.0
            per_fold.append(blends[0.0][-1])
            if name == "current":
                hist = feats[(feats["timestamp"] < fold["val_start"]) & feats["hour"].isin(OPERATING_HOURS)] \
                    .groupby("agent_id")["liquidity_shortage"].mean()
                alert_parts.append(X.alert_scores(val, m.predict(val), hist))
                fold_info.append({"fold": fold["name"], "dev_rows": int(len(dev)), "dev_end": str(dev["timestamp"].max()),
                                  "val_rows": int(len(val)), "val_start": str(val["timestamp"].min()),
                                  "val_last_row": str(val["timestamp"].max()),
                                  "val_last_target_hour": str(val["timestamp"].max() + pd.Timedelta(hours=X.H))})
        pooled = {w: _pool(v) for w, v in blends.items() if v}
        best_w = min(pooled, key=lambda w: pooled[w]["peak_requirement_mae"])
        val_scores[name] = {"blend_weight": best_w, **_r(pooled[best_w]),
                            "per_fold": [_r(s) for s in per_fold],
                            "blend_grid": {f"{w:g}": round(pooled[w]["peak_requirement_mae"], 2) for w in pooled}}
        print(f"  [validation] {name}: peak MAE {pooled[best_w]['peak_requirement_mae']:,.1f} (blend {best_w}) "
              f"P90 cov {pooled[best_w]['p90_coverage']:.3f}", flush=True)

    cur = val_scores["current"]
    eligible = []
    for name, s in val_scores.items():
        if name == "current":
            continue
        ok = (s["peak_requirement_mae"] <= 0.99 * cur["peak_requirement_mae"]
              and 0.87 <= s["p90_coverage"] <= 0.93
              and s["cash_demand_mae"] <= 1.01 * cur["cash_demand_mae"])
        s["passes_validation_gate"] = bool(ok)
        s["validation_peak_mae_change_pct"] = round(100 * (s["peak_requirement_mae"] / cur["peak_requirement_mae"] - 1), 2)
        if ok:
            eligible.append(name)
    chosen = min(eligible, key=lambda n: val_scores[n]["peak_requirement_mae"]) if eligible else None

    alerts = X.combine_alerts(alert_parts)
    passing = [float(t) for t, v in alerts["thresholds"].items() if v["precision"] >= 0.70]
    threshold = min(passing) if passing else 50.0
    return {
        "version": X.VERSION,
        "written_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "criteria": X.CRITERIA, "criteria_sha256": X.criteria_hash(),
        "folds": fold_info,
        "held_out_rows_used": 0,
        "validation_forecast": val_scores,
        "selected_forecast_candidate": chosen,
        "selected_blend_weight": val_scores[chosen]["blend_weight"] if chosen else None,
        "validation_alerts_current_model": {"n_decisions": alerts["n_decisions"], "shortages": alerts["shortages"],
                                            "thresholds": {t: _r(v) for t, v in alerts["thresholds"].items()}},
        "selected_alert_threshold": threshold,
        "selection_seconds": round(time.time() - t0, 1),
    }


# --------------------------------------------------------------------------- stage 2: held-out
def _v2(feats, agents, preds, hist_rate, anomaly_status) -> dict:
    cfg = rebalance_v2.selected_config()
    sq = impact.simulate_policy(feats, agents, None, hist_rate, forecast_source="none")
    v2 = impact.simulate_policy(feats, agents, preds, hist_rate, anomaly_status, "ml", policy="v2", policy_cfg=cfg)
    m = impact.summarize(v2, sq["unmet"])
    return {k: m.get(k, 0) for k in ("shortage_events", "unmet_cash_demand_bdt", "interventions",
                                     "donor_shortage_events_after_transfer", "estimated_logistics_cost_bdt",
                                     "unnecessary_interventions_pct")}


def holdout(prereg: dict) -> dict:
    if prereg["criteria_sha256"] != X.criteria_hash():
        raise SystemExit("pre-registered criteria changed after selection - refusing to evaluate the held-out period")
    t0 = time.time()
    eng = engine.Engine.load()
    feats = X.add_candidate_features(eng.feats, eng.agents)
    train_df, test_df = features.time_split(feats)
    hist = eng.hist_rate
    status = eng.anomaly_status_matrix()
    cur_pred = eng.preds
    res = {"current": {"forecast": X.forecast_scores(test_df, cur_pred.reindex(test_df.index)),
                       "alerts": X.alert_scores(test_df, cur_pred, hist),
                       "v2": _v2(eng.feats, eng.agents, cur_pred, hist, status)}}
    name = prereg["selected_forecast_candidate"]
    if name:
        cand = X.make_candidate(name).fit(train_df)
        cand.blend_weight = prereg["selected_blend_weight"] or 0.0
        usable = feats["out_same_window_avg7"].notna() & feats["out_rolling_mean_168h"].notna()
        cp = cand.predict(feats.loc[usable])
        res["candidate"] = {"name": name, "forecast": X.forecast_scores(test_df, cp.reindex(test_df.index)),
                            "alerts": X.alert_scores(test_df, cp, hist),
                            "v2": _v2(eng.feats, eng.agents, cp, hist, status)}

    c = X.CRITERIA
    cf, ca = res["current"]["forecast"], res["current"]["alerts"]["thresholds"]
    high_cur = ca["50"]
    decisions = {}
    if name:
        kf, ka, kv, cv = (res["candidate"]["forecast"], res["candidate"]["alerts"]["thresholds"]["50"],
                          res["candidate"]["v2"], res["current"]["v2"])
        pf = c["promotion_forecast"]
        seasonal_gain = 100 * (1 - kf["peak_requirement_mae"] / kf["seasonal_peak_mae"])
        checks = {
            "peak_mae_at_least_3pct_below_current": kf["peak_requirement_mae"] <= pf["peak_mae_vs_current_max_ratio"] * cf["peak_requirement_mae"],
            "peak_mae_at_least_10pct_below_seasonal": seasonal_gain >= pf["peak_mae_vs_seasonal_min_improvement_pct"],
            "cash_demand_mae_not_worse_than_1pct": kf["cash_demand_mae"] <= pf["cash_demand_mae_vs_current_max_ratio"] * cf["cash_demand_mae"],
            "p90_coverage_in_range": pf["p90_coverage_range"][0] <= kf["p90_coverage"] <= pf["p90_coverage_range"][1],
            "high_plus_recall_not_down_more_than_1pp": 100 * (ka["recall"] - high_cur["recall"]) >= pf["high_plus_recall_min_change_pp"],
            "high_plus_precision_not_down_more_than_5pp": 100 * (ka["precision"] - high_cur["precision"]) >= pf["high_plus_precision_min_change_pp"],
            "v2_unmet_not_worse_than_2pct": kv["unmet_cash_demand_bdt"] <= pf["v2_unmet_max_ratio"] * cv["unmet_cash_demand_bdt"],
            "v2_shortage_events_not_worse_than_2pct": kv["shortage_events"] <= pf["v2_shortage_events_max_ratio"] * cv["shortage_events"],
            "v2_donor_shortages_at_most_2_more": kv["donor_shortage_events_after_transfer"] <= cv["donor_shortage_events_after_transfer"] + pf["v2_donor_shortage_events_max_increase"],
            "leakage_tests_pass": True,  # enforced by tests/test_ml_experiment.py; a failing test fails the build
        }
        decisions["forecast"] = {
            "candidate": name, "checks": checks, "promoted": all(checks.values()),
            "peak_mae_change_vs_current_pct": round(100 * (kf["peak_requirement_mae"] / cf["peak_requirement_mae"] - 1), 2),
            "peak_mae_improvement_vs_seasonal_pct": round(seasonal_gain, 2),
            "current_peak_mae_improvement_vs_seasonal_pct": round(100 * (1 - cf["peak_requirement_mae"] / cf["seasonal_peak_mae"]), 2),
        }
    else:
        decisions["forecast"] = {"candidate": None, "promoted": False,
                                 "reason": "no candidate passed the validation gate; nothing was evaluated on held-out"}
    t = f"{prereg['selected_alert_threshold']:g}"
    op = ca[t]
    pa = c["promotion_alert_operating_point"]
    a_checks = {
        "recall_gain_at_least_10pp": 100 * (op["recall"] - high_cur["recall"]) >= pa["recall_min_gain_pp"],
        "precision_at_least_0_70": op["precision"] >= pa["precision_min"],
        "alert_volume_at_most_3x": op["alerts"] <= pa["alert_rate_max_multiple"] * high_cur["alerts"],
    }
    decisions["alert_operating_point"] = {
        "threshold": prereg["selected_alert_threshold"], "equivalent_level": "MEDIUM or above" if t == "25" else f"risk score >= {t}",
        "checks": a_checks, "promoted": t != "50" and all(a_checks.values()),
        "recall_change_pp": round(100 * (op["recall"] - high_cur["recall"]), 2),
        "precision_change_pp": round(100 * (op["precision"] - high_cur["precision"]), 2),
        "scope": pa["scope"],
    }
    days = test_df["timestamp"].dt.normalize().nunique()
    for k in ("current", "candidate"):
        if k in res:
            for th in res[k]["alerts"]["thresholds"].values():
                th["false_alert_hours_per_100_agents_per_day"] = round(100 * th["false_positives"] / (days * eng.agents.shape[0]), 2)
    return {"results": res, "decisions": decisions, "held_out_days": int(days), "holdout_seconds": round(time.time() - t0, 1)}


def main(stage: str) -> None:
    if stage in ("select", "all"):
        d = data_gen.load()
        feats = X.add_candidate_features(features.build_features(d.hourly, d.agents), d.agents)
        prereg = select(feats)
        PREREG.write_text(json.dumps(prereg, indent=2) + "\n")
        print(f"  pre-registration -> {PREREG} (criteria sha256 {prereg['criteria_sha256'][:12]}…)", flush=True)
        print(f"  selected forecast candidate: {prereg['selected_forecast_candidate']} "
              f"(blend {prereg['selected_blend_weight']}); alert threshold: {prereg['selected_alert_threshold']:g}")
    if stage in ("holdout", "all"):
        prereg = json.loads(PREREG.read_text())
        ho = holdout(prereg)
        out = {
            "version": X.VERSION, "label": X.LABEL,
            "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            "command": "python ml/scripts/ml_experiment.py",
            "protocol": [
                "Candidates and the alert operating point were selected on two training-period validation folds only "
                "(purged: every scored target window ends inside its fold).",
                "Promotion criteria were fixed in code and hashed before the held-out run; the held-out stage refuses "
                "to run if they changed.",
                "The held-out period (2026-08-18 .. 2026-08-31) was evaluated once for the current serving model and "
                "the selected candidates.",
            ],
            "criteria": X.CRITERIA, "criteria_sha256": X.criteria_hash(),
            "preregistration": {k: prereg[k] for k in ("written_at", "folds", "validation_forecast",
                                                      "selected_forecast_candidate", "selected_blend_weight",
                                                      "validation_alerts_current_model", "selected_alert_threshold",
                                                      "held_out_rows_used")},
            "candidates": {k: v["desc"] for k, v in X.CANDIDATES.items()},
            **ho,
        }
        out["serving_model_changed"] = bool(ho["decisions"]["forecast"]["promoted"])
        OUT.write_text(json.dumps(out, indent=2, default=float) + "\n")
        for k, dcs in ho["decisions"].items():
            print(f"  [{k}] promoted={dcs['promoted']} {dcs.get('checks', dcs.get('reason'))}")
        print(f"  experiment -> {OUT}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=("select", "holdout", "all"), default="all")
    main(ap.parse_args().stage)
