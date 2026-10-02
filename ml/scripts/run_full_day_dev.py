"""Phase 2E development check: full-day ML on DEVELOPMENT seeds 2026-2030, training period only.

Fits on agent-days before 2026-08-04 and validates on 2026-08-04 -> 2026-08-17 (both before the
held-out test period). Confirmatory seeds are never touched here. Writes
ml/artifacts_dual/full_day_dev_validation.json.

Usage:  python ml/scripts/run_full_day_dev.py
"""
from __future__ import annotations

import _bootstrap  # noqa: F401

import numpy as np
import pandas as pd

from agentflow import dual_world as dw, dual_world_eval as ev, forecast, full_day as fd


def main() -> None:
    per_seed = {}
    for seed in fd.DEV_SEEDS:
        assert seed not in fd.CONFIRMATORY_SEEDS
        world = dw.generate_world(seed=seed)
        daily = fd.build_daily(world.hourly, world.agents)
        dev = daily[daily["date"] < fd.DEV_VALIDATION_START]
        val = daily[(daily["date"] >= fd.DEV_VALIDATION_START) & (daily["date"] < fd.TEST_START)]
        assert val["date"].max() < fd.TEST_START
        models = fd.train(dev)
        preds = fd.predict(models, val)
        fm = fd.forecast_metrics(val, preds, with_groups=False)
        days = pd.DatetimeIndex(sorted(val["date"].unique()))
        sim = fd.simulate_policies(world.hourly, world.agents, val, preds, days)
        imp = fd.impact_summary(sim, with_harm=False)
        prim = {k: v["primary_operating_hours"]["combined_unmet_bdt"] for k, v in imp["policies"].items()}
        per_seed[str(seed)] = {"dev_rows": int(len(dev)), "val_rows": int(len(val)),
                               "dev_dates": [str(dev["date"].min().date()), str(dev["date"].max().date())],
                               "val_dates": [str(days[0].date()), str(days[-1].date())],
                               "forecast": fm, "combined_unmet_primary_bdt": prim,
                               "incremental_vs_seasonal_7d": imp["incremental_vs_comparator"],
                               "best_simple_policy": imp["best_simple_policy"],
                               "plausibility": fd.plausibility(fm, imp["conserved_all_policies"])}
        r = per_seed[str(seed)]
        print(f"[dev {seed}] cash MAE ML={fm['cash']['ml_p50']['mae']:,.0f} seas7={fm['cash']['baselines']['seasonal_requirement_7d']['mae']:,.0f} "
              f"P90cov={fm['cash']['p90']['empirical_coverage']:.3f} | efloat MAE ML={fm['efloat']['ml_p50']['mae']:,.0f} "
              f"seas7={fm['efloat']['baselines']['seasonal_requirement_7d']['mae']:,.0f} P90cov={fm['efloat']['p90']['empirical_coverage']:.3f} "
              f"| unmet incr vs seas7={r['incremental_vs_seasonal_7d']['combined_unmet_reduction_pct']:.1f}% broken={r['plausibility']['clearly_broken']}")
    art = {"label": "Development-world training-period validation only - NOT a project claim",
           "world_version": dw.WORLD_VERSION, "assumptions_version": dw.ASSUMPTIONS_VERSION,
           "protocol": "docs/FULL_DAY_ML_PROTOCOL.md", "dev_seeds": list(fd.DEV_SEEDS),
           "validation_window": [str(fd.DEV_VALIDATION_START.date()), "2026-08-17"],
           "per_seed": per_seed,
           "any_clearly_broken": any(r["plausibility"]["clearly_broken"] for r in per_seed.values()),
           "median_incremental_vs_seasonal_7d_pct": float(np.median(
               [r["incremental_vs_seasonal_7d"]["combined_unmet_reduction_pct"] for r in per_seed.values()]))}
    forecast.write_json(dw.ARTIFACTS_DIR / "full_day_dev_validation.json", ev._r(art))
    print("any clearly broken:", art["any_clearly_broken"], "| median incremental vs seasonal 7d:",
          round(art["median_incremental_vs_seasonal_7d_pct"], 2))


if __name__ == "__main__":
    main()
