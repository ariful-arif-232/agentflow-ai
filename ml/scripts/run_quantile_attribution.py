"""Phase 2F: cautious non-ML baseline attribution audit on fresh seeds 2036-2040 (research only).

Runs only with --confirm, after the implementation freeze (docs/QUANTILE_ATTRIBUTION_PROTOCOL.md).
First verifies that the frozen full-day ML (commit 3128176) reproduces the Phase 2E seed-2031 result,
then evaluates every policy on identical budgets, floors, allocator and demand. Writes
ml/artifacts_dual/quantile_attribution_seed_2036.json and quantile_attribution_multiseed.json.

Usage:  python ml/scripts/run_quantile_attribution.py --confirm
"""
from __future__ import annotations

import _bootstrap  # noqa: F401

import hashlib
import json
import sys

import numpy as np
import pandas as pd

from agentflow import config, dual_world as dw, dual_world_eval as ev, forecast, full_day as fd, ml_attribution as ma
from agentflow import prepositioning as pp, quantile_attribution as qa

ORACLE_LABEL = "ORACLE - evaluation only, impossible operationally"


def run_world(seed: int) -> dict:
    world = dw.generate_world(seed=seed)
    daily = fd.build_daily(world.hourly, world.agents)
    train, test = daily[daily["date"] < fd.TEST_START], daily[daily["date"] >= fd.TEST_START]
    models = fd.train(train)
    preds = fd.predict(models, test)
    days = pd.DatetimeIndex(sorted(test["date"].unique()))
    sim = qa.simulate(world.hourly, world.agents, test, preds, days)
    return {"world": world, "test": test, "preds": preds, "sim": sim, "forecast": fd.forecast_metrics(test, preds)}


def metrics(sim: dict) -> dict:
    return {k: {"primary_operating_hours": pp.service_metrics(s, sim["ro"], sim["ri"], sim["primary_mask"]),
                "secondary_continuous": pp.service_metrics(s, sim["ro"], sim["ri"], sim["secondary_mask"])}
            for k, s in sim["sims"].items()}


def regression_check() -> dict:
    """Frozen-ML regression: seed 2031 must reproduce Phase 2E exactly (ML and mean7 policies, forecasts)."""
    for path, digest in qa.FROZEN_SHA256.items():
        got = hashlib.sha256((config.REPO_ROOT / path).read_bytes()).hexdigest()
        if got != digest:
            raise SystemExit(f"frozen file changed: {path}")
    prev_imp = json.loads((dw.ARTIFACTS_DIR / "full_day_confirmatory_impact.json").read_text())["per_seed"][str(qa.REGRESSION_SEED)]
    prev_fc = json.loads((dw.ARTIFACTS_DIR / "full_day_confirmatory_forecast.json").read_text())["per_seed"][str(qa.REGRESSION_SEED)]
    r = run_world(qa.REGRESSION_SEED)
    m = metrics(r["sim"])
    pairs = {"ml_combined_unmet": (m[qa.ML]["primary_operating_hours"]["combined_unmet_bdt"],
                                   prev_imp["policies"]["full_day_ml_p90"]["primary_operating_hours"]["combined_unmet_bdt"]),
             "mean7_combined_unmet": (m[qa.MEAN7]["primary_operating_hours"]["combined_unmet_bdt"],
                                      prev_imp["policies"]["seasonal_requirement_7d"]["primary_operating_hours"]["combined_unmet_bdt"]),
             "ml_cash_mae": (r["forecast"]["cash"]["ml_p50"]["mae"], prev_fc["forecast"]["cash"]["ml_p50"]["mae"]),
             "ml_efloat_mae": (r["forecast"]["efloat"]["ml_p50"]["mae"], prev_fc["forecast"]["efloat"]["ml_p50"]["mae"])}
    ok = all(abs(a - b) <= 1e-3 * max(1.0, abs(b)) for a, b in pairs.values())
    if not ok:
        raise SystemExit(f"frozen ML regression FAILED: {pairs}")
    return {"seed": qa.REGRESSION_SEED, "frozen_spec_commit": qa.FROZEN_SPEC_COMMIT, "frozen_files_sha256_match": True,
            "reproduces_phase_2e": True, "values": {k: [float(a), float(b)] for k, (a, b) in pairs.items()}}


def main() -> None:
    if "--confirm" not in sys.argv:
        raise SystemExit("refusing to run: pass --confirm (seeds 2036-2040 are evaluated once, after the freeze)")
    reg = regression_check()
    print("frozen ML regression check:", reg["values"])
    per_seed, detail, cov = {}, None, {"cash": [0, 0], "efloat": [0, 0]}
    for seed in qa.AUDIT_SEEDS:
        assert seed not in qa.PRIOR_SEEDS
        r = run_world(seed)
        sim, fm = r["sim"], r["forecast"]
        m = metrics(sim)
        prim = {k: v["primary_operating_hours"] for k, v in m.items()}
        best = qa.best_cautious(prim)
        inc = ma.incremental(prim[qa.ML], prim[best])
        conserved = all(c["exact"] for c in sim["conservation"].values())
        for res in ("cash", "efloat"):
            cov[res][0] += fm[res]["p90"]["covered"]
            cov[res][1] += fm[res]["p90"]["n"]
        harm_sq = qa.harm_groups(sim, names=(best, qa.ML, qa.MEAN7), ref="status_quo")
        ml_vs_best = qa.harm_groups(sim, names=(qa.ML,), ref=best)[qa.ML]
        per_seed[str(seed)] = {
            "prim": prim, "incremental": inc, "conserved_all_policies": conserved,
            "best_cautious_non_ml": best, "conservation": sim["conservation"],
            "ml_p90_coverage": {res: fm[res]["p90"]["empirical_coverage"] for res in ("cash", "efloat")},
            "historical_signal_coverage": sim["historical_signal_coverage"],
            "forecast_mae": {res: {"ml_p50": fm[res]["ml_p50"]["mae"],
                                   "seasonal_mean7": fm[res]["baselines"]["seasonal_requirement_7d"]["mae"]} for res in ("cash", "efloat")},
            "harm_vs_status_quo": harm_sq, "ml_vs_best_cautious": ml_vs_best,
            "secondary_combined_unmet": {k: v["secondary_continuous"]["combined_unmet_bdt"] for k, v in m.items()},
        }
        if seed == qa.AUDIT_SEEDS[0]:
            detail = {"metrics": m, "forecast": fm, "network_daily_budget_bdt": sim["budgets"]}
        print(f"[audit {seed}] mean7={prim[qa.MEAN7]['combined_unmet_bdt']:,.0f} q90={prim[qa.Q90]['combined_unmet_bdt']:,.0f} "
              f"max7={prim[qa.MAX7]['combined_unmet_bdt']:,.0f} ML={prim[qa.ML]['combined_unmet_bdt']:,.0f} best={best} "
              f"incr={inc['combined_unmet_reduction_pct']:.2f}% cash={inc['cash_unmet_reduction_pct']:.2f}% "
              f"efloat={inc['efloat_unmet_reduction_pct']:.2f}% conserved={conserved}")
    bar = qa.attribution_bar(per_seed)
    keys = ("combined_unmet_reduction_pct", "cash_unmet_reduction_pct", "efloat_unmet_reduction_pct", "shortage_event_difference")
    summary = {k: {"mean": float(np.mean([per_seed[s]["incremental"][k] for s in per_seed])),
                   "median": float(np.median([per_seed[s]["incremental"][k] for s in per_seed])),
                   "min": float(min(per_seed[s]["incremental"][k] for s in per_seed)),
                   "max": float(max(per_seed[s]["incremental"][k] for s in per_seed))} for k in keys}
    pooled = {res: cov[res][0] / cov[res][1] for res in cov}
    common = {"label": "Synthetic held-out simulation - fresh seeds from the same Dual-Liquidity World v2 family (NOT external "
                       "or real-world validation) - cautious non-ML baseline attribution (research only)",
              "world_version": dw.WORLD_VERSION, "assumptions_version": dw.ASSUMPTIONS_VERSION,
              "protocol": "docs/QUANTILE_ATTRIBUTION_PROTOCOL.md", "audit_seeds": list(qa.AUDIT_SEEDS),
              "frozen_ml_spec_commit": qa.FROZEN_SPEC_COMMIT, "quantile_method": "linear interpolation (numpy method='linear'), q=0.90",
              "policies": list(qa.POLICIES), "oracle_label": ORACLE_LABEL, "bar": qa.BAR}
    forecast.write_json(dw.ARTIFACTS_DIR / "quantile_attribution_seed_2036.json",
                        ev._r({**common, "seed": 2036, **per_seed["2036"], **detail}))
    forecast.write_json(dw.ARTIFACTS_DIR / "quantile_attribution_multiseed.json",
                        ev._r({**common, "frozen_ml_regression_check": reg, "per_seed": per_seed,
                               "incremental_vs_best_cautious_summary": summary, "pooled_ml_p90_coverage": pooled,
                               "success_bar": bar}))
    print("pooled ML P90 coverage:", {k: round(v, 4) for k, v in pooled.items()})
    print("SUCCESS BAR:", bar)


if __name__ == "__main__":
    main()
