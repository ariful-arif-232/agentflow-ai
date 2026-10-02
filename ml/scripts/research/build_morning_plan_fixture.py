"""Build the Morning Liquidity Plan demo fixture and evidence artifact from the FROZEN research code.

This script is NOT part of the production pipeline and is never run by the API. It must be run with
the research checkout (commit c7418041f7b6c43873a8a45c1d43b32cafaf2a33, which contains the frozen
full-day ML of 3128176e23b4a5a2dde883e8dff8a75f21e35540) on the Python path:

    git worktree add /tmp/agentflow-research c7418041f7b6c43873a8a45c1d43b32cafaf2a33
    PYTHONPATH=/tmp/agentflow-research/ml python ml/scripts/research/build_morning_plan_fixture.py \
        --research-root /tmp/agentflow-research

Outputs (in this repository):
  ml/artifacts/morning_plan_demo.json      decision-time inputs only (no targets, outcomes or oracle)
  ml/artifacts/morning_plan_evidence.json  aggregate Phase 2E/2F research evidence and caveats

Seed 2036 is used only as a deterministic synthetic demo fixture; no performance claim is made from it.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

SOURCE_RESEARCH_COMMIT = "c7418041f7b6c43873a8a45c1d43b32cafaf2a33"
FROZEN_SPEC_COMMIT = "3128176e23b4a5a2dde883e8dff8a75f21e35540"
FROZEN_FULL_DAY_SHA256 = "0df1ff8ed3230974206e3dae410aa659bc5030fce464aa1580202f14f6bebfd1"
DEMO_SEED = 2036
OUT_DIR = Path(__file__).resolve().parents[3] / "ml" / "artifacts"


def r2(a) -> list:
    return [round(float(x), 2) for x in a]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--research-root", required=True, type=Path)
    args = ap.parse_args()
    root = args.research_root
    digest = hashlib.sha256((root / "ml/agentflow/full_day.py").read_bytes()).hexdigest()
    assert digest == FROZEN_FULL_DAY_SHA256, "research checkout does not contain the frozen full-day ML"

    from agentflow import dual_world as dw, full_day as fd, ml_attribution as ma  # research modules

    world = dw.generate_world(seed=DEMO_SEED)
    daily = fd.build_daily(world.hourly, world.agents)
    train, test = daily[daily["date"] < fd.TEST_START], daily[daily["date"] >= fd.TEST_START]
    preds = fd.predict(fd.train(train), test)
    ag = world.agents.sort_values("agent_id").reset_index(drop=True)
    ids = list(ag["agent_id"])
    dates = sorted(test["date"].unique())

    out_dates, max_diff = {}, 0
    for d in dates:
        rows = test[test["date"] == d].sort_values("agent_id")
        assert list(rows["agent_id"]) == ids
        p = preds.loc[rows.index]
        cash50, cash90 = r2(p["pred_cash_p50"]), r2(p["pred_cash_p90"])
        ef50, ef90 = r2(p["pred_efloat_p50"]), r2(p["pred_efloat_p90"])
        rc, re_, _ = ma.allocate(ag, np.array(cash90), np.array(ef90), "need")  # from the stored (rounded) inputs
        uc, ue, _ = ma.allocate(ag, p["pred_cash_p90"].to_numpy(), p["pred_efloat_p90"].to_numpy(), "need")
        max_diff = max(max_diff, int(np.abs(rc - uc).max()), int(np.abs(re_ - ue).max()))
        out_dates[str(pd.Timestamp(d).date())] = {
            "cash_p50": cash50, "cash_p90": cash90, "efloat_p50": ef50, "efloat_p90": ef90,
            "recommended_cash": [int(x) for x in rc], "recommended_efloat": [int(x) for x in re_]}

    fixture = {
        "meta": {"synthetic_data": True, "simulation_only": True, "demo_fixture": True,
                 "world_version": dw.WORLD_VERSION, "assumptions_version": dw.ASSUMPTIONS_VERSION,
                 "seed": DEMO_SEED, "frozen_model_spec_commit": FROZEN_SPEC_COMMIT,
                 "source_research_commit": SOURCE_RESEARCH_COMMIT,
                 "information_cutoff": "07:00", "allocation_time": "08:00", "horizon": "08:00-23:59",
                 "signal": "frozen full-day P90 cash and e-float requirement forecasts",
                 "floors_bdt": {"cash": 5000, "efloat": 5000},
                 "note": "Deterministic synthetic demo fixture. Decision-time inputs only: no realised demand, "
                         "targets, outcomes or oracle values. No performance claim is made from this seed.",
                 "parity_max_abs_diff_vs_unrounded_research_allocation_bdt": max_diff},
        "agents": [{"agent_id": a, "district": d, "location_cluster": c, "agent_volume_segment": s,
                    "status_quo_cash": int(round(tc)), "status_quo_efloat": int(round(te))}
                   for a, d, c, s, tc, te in zip(ag["agent_id"], ag["district"], ag["location_cluster"],
                                                 ag["agent_volume_segment"], ag["target_cash_level"], ag["target_efloat_level"])],
        "dates": out_dates,
    }

    qa = json.loads((root / "ml/artifacts_dual/quantile_attribution_multiseed.json").read_text())
    s = qa["incremental_vs_best_cautious_summary"]
    per = qa["per_seed"]
    mae = {r: float(np.median([100 * (1 - v["forecast_mae"][r]["ml_p50"] / v["forecast_mae"][r]["seasonal_mean7"])
                               for v in per.values()])) for r in ("cash", "efloat")}
    cov_hist = {sig: {r: [float(min(v["historical_signal_coverage"][sig][r] for v in per.values())),
                          float(max(v["historical_signal_coverage"][sig][r] for v in per.values()))] for r in ("cash", "efloat")}
                for sig in ("seasonal_requirement_q90_7d", "seasonal_requirement_max7")}
    evidence = {
        "label": "Historical synthetic research evidence - NOT measured upay performance and NOT an expected saving for any date",
        "synthetic_data": True, "world_family": f"{dw.WORLD_VERSION} (assumptions {dw.ASSUMPTIONS_VERSION})",
        "audit_seeds": [int(x) for x in qa["audit_seeds"]], "frozen_model_spec_commit": FROZEN_SPEC_COMMIT,
        "source_research_commit": SOURCE_RESEARCH_COMMIT,
        "comparison": "frozen full-day ML P90 vs best cautious non-ML baseline (historical 7-day q90, best in every audit seed)",
        "worlds_improved": int(qa["success_bar"]["seeds_ml_le_q90"]), "worlds_total": len(qa["audit_seeds"]),
        "pre_registered_bar_passed": bool(qa["success_bar"]["passes"]),
        "combined_unmet_reduction_pct": {"median": s["combined_unmet_reduction_pct"]["median"],
                                         "min": s["combined_unmet_reduction_pct"]["min"], "max": s["combined_unmet_reduction_pct"]["max"]},
        "cash_unmet_reduction_pct_median": s["cash_unmet_reduction_pct"]["median"],
        "efloat_unmet_reduction_pct_median": s["efloat_unmet_reduction_pct"]["median"],
        "exact_resource_conservation": all(v["conserved_all_policies"] for v in per.values()),
        "extra_working_capital_bdt": 0,
        "pooled_p90_coverage": {"cash": qa["pooled_ml_p90_coverage"]["cash"], "efloat": qa["pooled_ml_p90_coverage"]["efloat"],
                                "nominal": 0.90},
        "historical_signal_coverage_range": cov_hist,
        "forecast_mae_improvement_vs_mean7_median_pct": mae,
        "caveats": [
            "Synthetic world family only - not real upay data and not external validation.",
            "No guaranteed savings; results are historical synthetic simulations.",
            "Cash P90 coverage is about 85%, below the nominal 90%.",
            "Low-volume agents did worse than the cautious q90 baseline in 4 of 5 synthetic audit seeds.",
            "Rural e-float allocations can fall materially (about 0.55-0.66x status quo in the audit).",
            "Human review is required; the plan never moves money.",
        ],
        "research_path": [
            "Peer cash/e-float swaps rejected: local same-time complementarity was sparse (0/5 worlds met the bar).",
            "6-hour ML rejected for morning planning: a seasonal full-day history baseline beat it in 5/5 worlds.",
            "Horizon aligned to the decision: full-day ML beat the seasonal mean in 5/5 fresh confirmatory worlds.",
            "Final attribution: the frozen full-day ML beat cautious historical q90/max baselines in 5/5 fresh worlds.",
        ],
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "morning_plan_demo.json").write_text(json.dumps(fixture, separators=(",", ":")))
    (OUT_DIR / "morning_plan_evidence.json").write_text(json.dumps(evidence, indent=2))
    print("dates:", list(out_dates), "| parity max diff:", max_diff,
          "| fixture bytes:", (OUT_DIR / "morning_plan_demo.json").stat().st_size)


if __name__ == "__main__":
    main()
