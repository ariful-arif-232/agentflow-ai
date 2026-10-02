# Dual-Liquidity Experiment (research branch only)

> **Experimental — NOT deployed and NOT merged.** This branch (`research/dual-liquidity-groundwork`)
> preserves forecasting groundwork for a possible future phase. `main` remains the validated
> cash-side AgentFlow system (Track 05: Merchant & Agent Intelligence — Agent Liquidity Forecasting),
> with rebalancing policy V2 as the default and V1 for comparison. All data is synthetic.

## Idea

An MFS agent manages two coupled resources: physical cash supports cash-out, while e-float supports
cash-in. Each transaction shifts value from one side to the other. The experiment asked whether
AgentFlow could forecast e-float pressure the same way it forecasts cash pressure.

## What this branch adds (additive; legacy cash code paths unchanged)

* **E-float requirement target** (`ml/agentflow/features.py`). The target
  `future_6h_net_efloat_demand = max(0, max_k Σ_{j=1..k} (cash_in − cash_out))` is computed over the
  *requested* flow. It mirrors the existing cash target and is not a record of failed cash-in.
* **Same-window history features.** `efloat_req_same_window_{1d,7d,avg7,max7}` are shifted by at
  least 24 h, so each source window is fully observed at decision time. Only `1d`, `7d` and `avg7`
  are model features.
* **Two e-float models** (`ml/agentflow/forecast.py`): `efloat_requirement` (P50) and
  `efloat_requirement_p90` (0.9 quantile). They use the same HistGradientBoosting family and
  settings as the cash requirement models and `EFLOAT_FEATURES`. P90 ≥ P50 ≥ 0 is enforced. The
  cash models still use exactly `FORECAST_FEATURES`.
* **`ml/agentflow/dual.py`**:
  * e-float pressure fields: coverage ratios, expected gap and P90 gap;
  * a deterministic `liquidity_state` (HEALTHY / WATCH / CASH_PRESSURE / EFLOAT_PRESSURE /
    DUAL_PRESSURE);
  * template-based English and Bangla explanations;
  * evaluation helpers;
  * a training-period validation check.
* **Cash-only training switch** (`policy_selection.py`). Policy-validation folds train cash models
  only (`include_efloat=False`), so V2 parameter selection is unaffected.

This branch has no API, UI, test or documentation integration beyond this note.

## Legacy regression check

With this code, the full pipeline (`python ml/scripts/run_pipeline.py`) reproduced `metrics.json`,
`impact.json`, `policy_selection.json` and `dataset_summary.json` **byte-for-byte**:

| Policy | Shortage events | Unmet cash demand (BDT) | Transfers |
|---|---|---|---|
| V1 | 1,255 | 58,27,590 | 501 |
| V2 (default) | 1,223 | 56,90,940 | 345 |

Only `training_metadata.json` would change, because it lists the extra models. That change is not
committed.

## Results — training-period validation only

**No final held-out e-float evaluation was performed.** The 14-day test period was never used for
e-float work.

The models were fitted on data up to 2026-08-03 and scored on 2026-08-04 → 2026-08-17. Both windows
fall before the held-out test period.

| E-float requirement (next 6 h) | MAE (BDT) |
|---|---|
| ML (P50) | ≈ 2,660 |
| Naive (same window yesterday) | ≈ 3,468 |
| Seasonal (7-day same-window average) | ≈ 2,700 |

* ML improves on naive by about 23%, but on the seasonal baseline by only about 1.5%.
* P90 empirical coverage is about 90.4% (nominal 90%).

## Why the experiment stopped

E-float pressure (`efloat_balance < actual future_6h_net_efloat_demand`) was **essentially absent**
in the legacy synthetic world:

* there were 0 cases at operating hours in the validation window;
* about 0.002% of training-period rows had pressure.

**The reason:** the generator resets each agent's e-float every morning to 0.9 × its daily cash-out.
That is typically more than 30× the next-6h e-float requirement. Applying the cash provisioning
rule to e-float instead still gave only about 0.06%.

With almost no positive cases, e-float pressure precision and recall would be meaningless.
`liquidity_state` would simply repeat the cash risk.

**We deliberately did NOT tune the synthetic world to manufacture positive cases.** Creating real
e-float stress means changing the cash-in stream, which would change the cash history and the
validated V1/V2 results.

## Next design

A **separately versioned, resource-conserving dual-liquidity synthetic world** would:

* model cash and e-float as coupled, binding constraints, with declined cash-in recorded;
* run alongside a matching resource-conserving simulator;
* keep the legacy world and its V1/V2 results unchanged for comparison.

The e-float pressure evaluation, any dual liquidity state shown to users and any dual-sided impact
claim must be validated in that world first.
