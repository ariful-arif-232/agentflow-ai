"""Evaluate trained models on the held-out test period and write ml/artifacts/metrics.json.

Usage:  python ml/scripts/evaluate.py
"""
from __future__ import annotations

import _bootstrap  # noqa: F401

from agentflow import anomaly, config, engine, evaluation, forecast


def main() -> None:
    eng = engine.Engine.load()
    feats = eng.feats
    from agentflow.features import time_split
    _, test_df = time_split(feats)

    metrics = {"label": "Synthetic held-out evaluation",
               "forecast": forecast.evaluate(eng.bundle, test_df)}
    metrics["forecast"]["feature_importance_cash_demand"] = forecast.feature_importance(eng.bundle, test_df)[:15]

    test_mask = feats["timestamp"] >= config.TEST_START
    metrics["anomaly"] = anomaly.evaluate(eng.detector, eng.anom.loc[test_mask, anomaly.ANOMALY_FEATURES],
                                          feats.loc[test_mask, "known_anomaly_label"],
                                          feats.loc[test_mask, "anomaly_type"])
    metrics["risk_alerts"] = evaluation.risk_alert_evaluation(feats[test_mask], eng.preds, eng.hist_rate)
    forecast.write_json(config.ARTIFACTS_DIR / "metrics.json", metrics)

    for name, e in metrics["forecast"]["targets"].items():
        ml = e["ml_model"]
        print(f"[{name}] ML MAE={ml['mae']:,.0f} RMSE={ml['rmse']:,.0f} WAPE={ml['wape']:.3f}")
        for b, m in e["baselines"].items():
            print(f"    baseline {b}: MAE={m['mae']:,.0f} RMSE={m['rmse']:,.0f}")
        print(f"    MAE improvement vs best baseline: {e['improvement_vs_best_baseline']['mae_pct']:.1f}%")
    print("P90 coverage:", round(metrics["forecast"]["quantile_p90"]["empirical_coverage"], 3))
    a = metrics["anomaly"]
    print(f"[anomaly] ROC-AUC={a['roc_auc']:.3f} AP={a['average_precision']:.3f}")
    for v, m in metrics["risk_alerts"]["variants"].items():
        print(f"[risk alerts:{v}] precision={m['precision']:.3f} recall={m['recall']:.3f} AUC={m['roc_auc']:.3f}")
    print("metrics ->", config.ARTIFACTS_DIR / "metrics.json")

    imp = eng.run_impact()
    forecast.write_json(config.ARTIFACTS_DIR / "impact.json", imp)
    for name, m in imp["policies"].items():
        print(f"[impact:{name}] shortage_events={m['shortage_events']:,} unmet=BDT {m['unmet_cash_demand_bdt']:,.0f} "
              f"availability={m['service_availability_pct']:.2f}% interventions={m['interventions']}")
    for key, name in (("agentflow_vs_status_quo", "V1"), ("agentflow_v2_vs_status_quo", "V2")):
        d = imp[key]
        print(f"AgentFlow {name} vs status quo: shortage events -{d['shortage_events_reduction_pct']:.1f}%, "
              f"unmet demand -{d['unmet_demand_reduction_pct']:.1f}%")
    dec = imp["deployment_decision"]
    print("deployment decision:", dec["default_policy"], dec["checks"])
    print("impact ->", config.ARTIFACTS_DIR / "impact.json")


if __name__ == "__main__":
    main()
