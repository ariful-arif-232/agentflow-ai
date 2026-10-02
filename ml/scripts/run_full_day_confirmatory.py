"""Phase 2E CONFIRMATORY evaluation of full-day ML on fresh seeds 2031-2035 (research only).

Runs only with --confirm, and only after the model-specification freeze commit has been pushed
(docs/FULL_DAY_ML_PROTOCOL.md). Trains the frozen full-day models on each world's training period,
evaluates forecasts on the held-out days, replays every allocation policy on identical budgets,
floors, allocator and demand, and applies the frozen A-E success bar. Writes
ml/artifacts_dual/full_day_confirmatory_forecast.json and full_day_confirmatory_impact.json.

Usage:  python ml/scripts/run_full_day_confirmatory.py --confirm
"""
from __future__ import annotations

import _bootstrap  # noqa: F401

import sys

import numpy as np
import pandas as pd
from sklearn.inspection import permutation_importance

from agentflow import config, dual_world as dw, dual_world_eval as ev, forecast, full_day as fd


def importance(models: dict, test: pd.DataFrame) -> dict:
    out = {}
    for r in ("cash", "efloat"):
        m = models[f"full_day_{r}_requirement_p50"]
        res = permutation_importance(m, test[fd.FEATURES], test[fd.TARGETS[r]], scoring="neg_mean_absolute_error",
                                     n_repeats=3, random_state=config.SEED, n_jobs=1)
        rows = sorted(zip(fd.FEATURES, res.importances_mean), key=lambda t: -t[1])[:10]
        out[r] = [{"feature": f, "mae_increase_bdt": float(v)} for f, v in rows]
    return out


def main() -> None:
    if "--confirm" not in sys.argv:
        raise SystemExit("refusing to run: pass --confirm (confirmatory seeds are evaluated once, after the spec freeze)")
    fc_seeds, imp_seeds, cov = {}, {}, {"cash": [0, 0], "efloat": [0, 0]}
    for seed in fd.CONFIRMATORY_SEEDS:
        assert seed not in fd.DEV_SEEDS
        world = dw.generate_world(seed=seed)
        daily = fd.build_daily(world.hourly, world.agents)
        train = daily[daily["date"] < fd.TEST_START]
        test = daily[daily["date"] >= fd.TEST_START]
        models = fd.train(train)
        preds = fd.predict(models, test)
        fm = fd.forecast_metrics(test, preds)
        for r in ("cash", "efloat"):
            cov[r][0] += fm[r]["p90"]["covered"]
            cov[r][1] += fm[r]["p90"]["n"]
        days = pd.DatetimeIndex(sorted(test["date"].unique()))
        sim = fd.simulate_policies(world.hourly, world.agents, test, preds, days)
        imp = fd.impact_summary(sim)
        fc_seeds[str(seed)] = {"train_rows": int(len(train)), "test_rows": int(len(test)),
                               "train_dates": [str(train["date"].min().date()), str(train["date"].max().date())],
                               "test_dates": [str(days[0].date()), str(days[-1].date())],
                               "forecast": fm, "top_permutation_importance_p50": importance(models, test)}
        imp_seeds[str(seed)] = imp
        p = {k: v["primary_operating_hours"] for k, v in imp["policies"].items()}
        i = imp["incremental_vs_comparator"]
        print(f"[confirm {seed}] seas7={p[fd.COMPARATOR]['combined_unmet_bdt']:,.0f} ML={p[fd.ML_POLICY]['combined_unmet_bdt']:,.0f} "
              f"incr={i['combined_unmet_reduction_pct']:.2f}% cash={i['cash_unmet_reduction_pct']:.2f}% efloat={i['efloat_unmet_reduction_pct']:.2f}% "
              f"best_simple={imp['best_simple_policy']} conserved={imp['conserved_all_policies']} "
              f"P90cov cash={fm['cash']['p90']['empirical_coverage']:.3f} efloat={fm['efloat']['p90']['empirical_coverage']:.3f}")
    pooled = {r: cov[r][0] / cov[r][1] for r in cov}
    bar = fd.confirmatory_bar({s: {"incremental": imp_seeds[s]["incremental_vs_comparator"],
                                   "conserved_all_policies": imp_seeds[s]["conserved_all_policies"]} for s in imp_seeds}, pooled)
    keys = ("combined_unmet_reduction_pct", "cash_unmet_reduction_pct", "efloat_unmet_reduction_pct", "shortage_event_difference")
    summary = {k: {"mean": float(np.mean([imp_seeds[s]["incremental_vs_comparator"][k] for s in imp_seeds])),
                   "median": float(np.median([imp_seeds[s]["incremental_vs_comparator"][k] for s in imp_seeds])),
                   "min": float(min(imp_seeds[s]["incremental_vs_comparator"][k] for s in imp_seeds)),
                   "max": float(max(imp_seeds[s]["incremental_vs_comparator"][k] for s in imp_seeds))} for k in keys}
    common = {"label": "CONFIRMATORY synthetic held-out simulation - Dual-Liquidity World v2 - full-day ML (research only)",
              "world_version": dw.WORLD_VERSION, "assumptions_version": dw.ASSUMPTIONS_VERSION,
              "protocol": "docs/FULL_DAY_ML_PROTOCOL.md", "confirmatory_seeds": list(fd.CONFIRMATORY_SEEDS),
              "features": fd.FEATURES, "model_specs": fd.MODEL_SPECS,
              "explanation": "The model predicts the resource requirement for the same operational horizon that the "
                             "morning allocation must cover. Importances describe the model, not causes."}
    forecast.write_json(dw.ARTIFACTS_DIR / "full_day_confirmatory_forecast.json",
                        ev._r({**common, "per_seed": fc_seeds, "pooled_p90_coverage": pooled}))
    forecast.write_json(dw.ARTIFACTS_DIR / "full_day_confirmatory_impact.json",
                        ev._r({**common, "comparator": fd.COMPARATOR, "per_seed": imp_seeds,
                               "incremental_vs_comparator_summary": summary, "success_bar": bar}))
    print("pooled P90 coverage:", {k: round(v, 4) for k, v in pooled.items()})
    print("SUCCESS BAR:", bar)


if __name__ == "__main__":
    main()
