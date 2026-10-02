# Full-Day ML Liquidity Forecast — Confirmatory Protocol (Phase 2E)

> **Research only.** Branch `research/full-day-ml-confirmatory`. This is not merged and not deployed.
> `main` and production are unchanged. All data is **synthetic** (Dual-Liquidity World v2,
> assumptions **2A.1**, unchanged). The evaluation is a held-out **simulation**; nothing moves real
> money.

This protocol is committed and pushed **before** any confirmatory world is generated. The **final
model specification** is committed and pushed in a separate later commit, **before** any confirmatory
seed is evaluated. The constants live in `ml/agentflow/full_day.py` and a test pins them.

## Question

> Can a **full-operating-day** ML forecast add decision value beyond the strong non-ML
> `seasonal_requirement_7d` baseline for the 08:00 Morning Liquidity Plan?

Phase 2D showed that the 6-hour ML signal loses to `seasonal_requirement_7d` in all five worlds,
most likely because of a **horizon mismatch**. This phase builds a model for the same horizon that
the morning plan must cover.

## 1. Seeds

| Role | Seeds | Allowed use |
|---|---|---|
| **Development** | 2026, 2027, 2028, 2029, 2030 | debugging, feature checks, **training-period chronological validation only**; never the final claim |
| **Confirmatory** | **2031, 2032, 2033, 2034, 2035** | generated and evaluated **once**, after the model-spec freeze; no seed dropped or added |

Both sets use the unchanged world assumptions 2A.1. The two seed sets are disjoint (tested). A
rerun is allowed only to check determinism, with identical code, configuration and seeds.

## 2. Decision, horizon and targets

* **Information cutoff: 07:00** on day *d*. Operational features use only completed days *≤ d−1*,
  so they are known well before 07:00.
* **Allocation:** at 08:00 on day *d* (the existing reset). **Planning horizon: 08:00–23:59 on day
  *d*** (the operating day, hours 08–23).
* **Targets** for each agent-day, computed from **requested** flows over hours 08–23 of day *d*:
  * `full_day_cash_requirement = max(0, max_k Σ_{h=08..k} (requested_cash_out − requested_cash_in))`
  * `full_day_efloat_requirement = max(0, max_k Σ_{h=08..k} (requested_cash_in − requested_cash_out))`

  These are the opening quantities needed to serve the whole operating day's requested flow under the
  within-hour net-settlement assumption.
* **One row per agent-day.** A row exists only once 7 complete prior days of history are available.
  No served or unmet outcome is ever a feature.

## 3. Pre-registered feature set (known by 07:00)

All "daily" quantities use the operating window (hours 08–23) of **prior** days.

| Group | Features |
|---|---|
| Static | `district_code`, `location_cluster_code`, `agent_type_code`, `agent_volume_segment_code`, `market_day` |
| Calendar (known in advance) | `day_of_week`, `is_weekend`, `day_of_month`, `is_salary_period`, `is_market_day` |
| Recent daily history | `prev_cash_out`, `prev_cash_in`, `prev_cash_req`, `prev_efloat_req` |
| Rolling history | `cash_out_mean3`, `cash_out_mean7`, `cash_in_mean3`, `cash_in_mean7`, `cash_req_mean7`, `cash_req_max7`, `efloat_req_mean7`, `efloat_req_max7`, `cash_req_std7`, `efloat_req_std7` |
| Same weekday | `cash_req_lag7`, `efloat_req_lag7`, `cash_req_sw_mean`, `efloat_req_sw_mean` (mean of the available same-weekday values at lags 7 and 14) |
| Trend | `cash_out_trend` (= mean3 / mean7), `cash_in_trend` |

The models never see `flow_event` labels, anomaly labels, the generator's hidden parameters or
shocks, held-out targets, or any confirmatory-world statistic.

## 4. Model family and specification

* The existing project family, `sklearn.ensemble.HistGradientBoostingRegressor`, with the
  **legacy settings**:
  * `learning_rate=0.06`, `max_iter=400`, `max_leaf_nodes=48`;
  * `min_samples_leaf=60`, `l2_regularization=1.0`;
  * `early_stopping=False`, `random_state=2026`;
  * the same categorical handling as the legacy models.
* **Four models:**

  | Model | Loss |
  |---|---|
  | `full_day_cash_requirement_p50` | squared error |
  | `full_day_cash_requirement_p90` | 0.9 quantile |
  | `full_day_efloat_requirement_p50` | squared error |
  | `full_day_efloat_requirement_p90` | 0.9 quantile |

* **P90 ≥ P50 ≥ 0** is enforced.
* **Training rows:** agent-days before 2026-08-18. **Held-out:** 2026-08-18 → 2026-08-31.

## 5. Development check (before the spec freeze)

* Development seeds only, training period only:
  * fit on agent-days before 2026-08-04;
  * validate on 2026-08-04 → 2026-08-17;
  * report forecast metrics and a validation-window allocation replay.
* The pre-registered features and settings above are **not tuned**. They may change only if
  development validation is **clearly broken**, defined as **any** of:
  1. aggregate P90 coverage outside **[70%, 99%]** for either resource;
  2. ML P50 MAE **worse than naive yesterday** on **both** resources;
  3. non-conservation;
  4. a leakage or implementation bug.

  Any such fix will be recorded with its reason before the freeze.

## 6. Baselines and policies

**Forecast baselines:**
* `yesterday_full_day_requirement`;
* `seasonal_requirement_7d` (mean of the previous 7 complete days' full-day requirement);
* `seasonal_same_weekday` (the requirement 7 days earlier).

**Allocation policies:** identical district budgets, BDT 5,000 floors, the Phase 2C/2D need-first
allocator (`ml_attribution.allocate`, mode `need`), the same held-out demand and the same operating
day. Only the signal differs.

| Policy | Signal |
|---|---|
| `status_quo` | fixed targets |
| `yesterday_requirement` | previous day's full-day requirement |
| `seasonal_requirement_7d` | 7-day mean full-day requirement |
| `seasonal_same_weekday` | full-day requirement 7 days earlier |
| `full_day_ml_p90` | full-day P90 cash and e-float forecasts |
| `oracle_full_day` | actual full-day requirement. ORACLE — evaluation only, impossible operationally |

The comparator named in the bar is `seasonal_requirement_7d`. If another simple baseline beats it in
any seed, that is reported prominently as a robustness result.

**Impact metrics:**
* **Primary:** operating hours 08:00–23:59 of the 14 held-out days.
* **Secondary:** the continuous window 08-18 08:00 → 08-31 23:00 (as in Phase 2C/2D).

## 7. Confirmatory success bar (frozen now)

Full-day ML adds meaningful value **only if all** of the following hold on seeds 2031–2035:

* **A.** ML combined unmet ≤ `seasonal_requirement_7d` combined unmet in **at least 4 of 5** seeds.
* **B.** The **median** incremental combined-unmet reduction versus `seasonal_requirement_7d` is
  **≥ 5%**.
* **C.** ML worsens cash *or* e-float unmet by **more than 5%** versus `seasonal_requirement_7d` in
  **at most 1** seed.
* **D.** **Exact** district cash and e-float conservation holds for every policy in every world.
* **E.** Aggregate held-out P90 empirical coverage (pooled over the 5 seeds) is within
  **[85%, 95%]** for **each** resource.

Incremental reduction is `100 × (seasonal − ML) / seasonal`, computed on primary-window unmet. The
bar is not changed after results are seen.

## 8. Reporting

The report covers:
* forecast metrics for cash and e-float (MAE, RMSE, WAPE, bias), and improvement over the best
  simple baseline and over naive yesterday;
* P90 coverage and interval width;
* results by location cluster and volume segment;
* agents better and worse, total benefit and harm, and worst-harmed agents;
* group allocation ratios and unmet change;
* top permutation-importance drivers, which do not imply causality.

Recommended wording: *"The model predicts the resource requirement for the same operational horizon
that the morning allocation must cover."*
