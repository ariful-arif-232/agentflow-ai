"""Evaluate trained models on the held-out test period and write ml/artifacts/metrics.json.

Usage:  python ml/scripts/evaluate.py
"""
from __future__ import annotations

import _bootstrap  # noqa: F401

from agentflow import config, data_gen, features, forecast


def main() -> None:
    data = data_gen.load()
    feats = features.build_features(data.hourly, data.agents)
    _, test_df = features.time_split(feats)
    bundle = forecast.ForecastBundle.load()

    metrics = {"label": "Synthetic held-out evaluation", **forecast.evaluate(bundle, test_df)}
    metrics["feature_importance_cash_demand"] = forecast.feature_importance(bundle, test_df)[:15]
    forecast.write_json(config.ARTIFACTS_DIR / "metrics.json", metrics)

    for name, e in metrics["targets"].items():
        ml = e["ml_model"]
        print(f"[{name}] ML MAE={ml['mae']:,.0f} RMSE={ml['rmse']:,.0f} WAPE={ml['wape']:.3f}")
        for b, m in e["baselines"].items():
            print(f"    baseline {b}: MAE={m['mae']:,.0f} RMSE={m['rmse']:,.0f}")
        print(f"    improvement vs best baseline: MAE {e['improvement_vs_best_baseline']['mae_pct']:.1f}%")
    print("P90 coverage:", round(metrics["quantile_p90"]["empirical_coverage"], 3))
    print("metrics ->", config.ARTIFACTS_DIR / "metrics.json")


if __name__ == "__main__":
    main()
