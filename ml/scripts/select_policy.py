"""Select Rebalancing Policy V2 parameters on training-period validation folds.

The held-out test period is NOT used here. Writes ml/artifacts/policy_selection.json,
which evaluate.py and the API read for the V2 configuration.

Usage:  python ml/scripts/select_policy.py
"""
from __future__ import annotations

import _bootstrap  # noqa: F401

from agentflow import config, engine, forecast, policy_selection


def main() -> None:
    eng = engine.Engine.load()
    res = policy_selection.select(eng.feats, eng.agents, eng.anomaly_status_matrix())
    forecast.write_json(config.ARTIFACTS_DIR / "policy_selection.json", res)
    v1 = res["v1_validation_total"]
    print(f"V1 (validation, both folds): transfers={v1['interventions']:.0f} donor_events={v1['donor_shortage_events_after_transfer']:.0f} "
          f"unnecessary={v1['unnecessary_interventions_pct']:.1f}% avoided/1k cost={v1['unmet_avoided_per_1000_cost_bdt']:,.0f}")
    print(policy_selection.summary_table(res["grid_results"]).to_string(index=False))
    print("outcome:", res["outcome"])
    print("selected:", {k: res["selected_config"][k] for k in policy_selection.RebalanceV2Config.tunable_fields()})
    print("policy selection ->", config.ARTIFACTS_DIR / "policy_selection.json")


if __name__ == "__main__":
    main()
