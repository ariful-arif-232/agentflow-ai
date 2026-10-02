"""Generate and evaluate the Dual-Liquidity Synthetic World v2 (research only).

Reads/writes ml/data_dual, ml/models_dual and ml/artifacts_dual only; the legacy world, models and
artifacts are never touched. Deterministic: the same seed reproduces identical artifacts
(training_metadata.json additionally records wall-clock fit times).

Usage:  python ml/scripts/run_dual_world.py
"""
from __future__ import annotations

import _bootstrap  # noqa: F401

from agentflow import dual_world as dw, dual_world_eval as ev, forecast


def main() -> None:
    world = dw.generate_world()
    dw.save(world)
    print(f"[{dw.WORLD_VERSION} / assumptions {dw.ASSUMPTIONS_VERSION}] rows={len(world.hourly):,} -> {dw.DATASET_PATH}")
    arts = ev.run(world)
    for name, obj in arts.items():
        forecast.write_json(dw.ARTIFACTS_DIR / name, obj)
        print("wrote", dw.ARTIFACTS_DIR / name)

    fm, sq = arts["forecast_metrics.json"], arts["status_quo_impact.json"]
    for k in ("cash_requirement", "efloat_requirement"):
        e = fm["held_out"][k]
        print(f"[held-out {k}] ML MAE={e['ml_model']['mae']:,.0f} best baseline={e['best_baseline']} "
              f"({e['baselines'][e['best_baseline']]['mae']:,.0f}) improvement={e['improvement_vs_best_baseline']['mae_pct']:.1f}% "
              f"P90 coverage={e['quantile_p90']['empirical_coverage']:.3f}")
    s = sq["held_out_service"]
    print(f"[status quo] cash fill={s['cash_side']['cash_out_fill_rate']:.4f} e-float fill={s['efloat_side']['cash_in_fill_rate']:.4f} "
          f"combined={s['network']['combined_value_fill_rate']:.4f}")
    v = sq["validity_for_phase_2b"]
    print("[validity]", {k: (x["rate"], x["rows"], x["agents"], x["passes"]) for k, x in v["sides"].items()}, "passes:", v["passes"])


if __name__ == "__main__":
    main()
