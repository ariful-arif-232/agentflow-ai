# Full-Day ML Liquidity Forecast — Confirmatory Results (Phase 2E)

> **Research only.** Branch `research/full-day-ml-confirmatory`; not merged and not deployed.
> **Confirmatory synthetic held-out simulation, Dual-Liquidity World v2 (assumptions 2A.1).** No
> real money moved. These results say nothing about real upay performance.

## Timeline (all commits signed and pushed in this order)

| Commit | Step |
|---|---|
| `80310d4` | Protocol pre-registered ([FULL_DAY_ML_PROTOCOL.md](FULL_DAY_ML_PROTOCOL.md)), with seeds, horizon, features, model, baselines, allocator and bar. |
| `3128176` | **Final model specification frozen**, with the development check, before any confirmatory world was generated. |
| `a7369b0` | **One-time** confirmatory evaluation on fresh seeds 2031–2035. A determinism rerun with identical code, config and seeds reproduced both artifacts byte-for-byte. |

## A. Final model specification (frozen)

* **Decision:**
  * information cutoff 07:00;
  * features use only completed prior days;
  * allocation at 08:00;
  * horizon is the operating day, 08:00–23:59.
* **Targets** for each agent-day, from requested flows over hours 08–23:
  * `full_day_cash_requirement = max(0, max cumsum(out − in))`;
  * `full_day_efloat_requirement = max(0, max cumsum(in − out))`.
* **Rows:** one per agent-day once 7 prior days exist. That gives 54 training days × 200 agents =
  10,800 rows per world.
* **Features (30):**
  * static: district, cluster, agent type, segment, market day;
  * calendar: weekday, weekend, day of month, salary period, market today;
  * previous-day cash-out, cash-in and cash/e-float requirement;
  * 3- and 7-day means of cash-out and cash-in;
  * 7-day mean, max and std of each requirement;
  * same-weekday lag 7 and the mean of lags 7 and 14;
  * 3/7-day cash-out and cash-in trend.
* **Models:** four `HistGradientBoostingRegressor` models with the legacy settings (`lr 0.06`,
  `max_iter 400`, `max_leaf_nodes 48`, `min_samples_leaf 60`, `l2 1.0`, seed 2026). P50 uses squared
  error and P90 uses the 0.9 quantile, with P90 ≥ P50 ≥ 0 enforced.
* **Allocation signal:** the full-day P90 cash and e-float forecasts. The allocator is the
  unchanged Phase 2C/2D need-first one, with the same district budgets and BDT 5,000 floors.

## B. Development-world check (training period only; not a claim)

Seeds 2026–2030 were fitted on data before 2026-08-04 and validated on 2026-08-04 → 2026-08-17:

| Seed | Cash MAE: ML / seasonal 7d | E-float MAE: ML / seasonal 7d | P90 coverage cash / e-float | Unmet vs seasonal 7d |
|---|---|---|---|---|
| 2026 | 9,559 / 10,836 | 11,410 / 14,011 | 86.4% / 90.2% | −13.6% |
| 2027 | 8,705 / 9,990 | 10,578 / 13,152 | 84.4% / 90.9% | −30.4% |
| 2028 | 10,526 / 11,593 | 10,845 / 13,169 | 83.8% / 90.1% | −18.7% |
| 2029 | 9,611 / 10,959 | 11,617 / 13,881 | 84.7% / 90.2% | −30.3% |
| 2030 | 8,940 / 10,341 | 11,188 / 13,544 | 85.1% / 89.2% | −38.3% |

No seed met any "clearly broken" criterion, so **nothing was changed**. Cash P90 coverage at 84–86%
was noted in the freeze commit as a risk for criterion E.

## C. Confirmatory results — fresh seeds 2031–2035

The primary window is the operating hours 08:00–23:59 of the 14 held-out days (2026-08-18 → 08-31).
Unmet amounts are in BDT.

| Seed | Status quo | Seasonal 7d | **Full-day ML** | ML vs seasonal: combined | Cash | E-float | Shortage events (seasonal → ML) | Conservation |
|---|---|---|---|---|---|---|---|---|
| 2031 | 73,41,580 | 32,96,539 | **16,97,295** | **−48.5%** | −48.2% | −48.9% | 536 → 275 | exact |
| 2032 | 84,89,820 | 42,60,255 | **33,38,231** | **−21.6%** | −67.2% | −11.1% | 546 → 438 | exact |
| 2033 | 92,65,330 | 42,35,901 | **30,63,510** | **−27.7%** | −63.1% | −17.6% | 564 → 429 | exact |
| 2034 | 69,64,110 | 31,67,421 | **18,64,801** | **−41.1%** | −53.9% | −33.3% | 512 → 294 | exact |
| 2035 | 85,74,130 | 44,58,550 | **29,78,805** | **−33.2%** | −46.7% | −19.9% | 598 → 453 | exact |

Negative values mean ML has less unmet demand than seasonal 7d.

**Incremental reduction versus seasonal 7d:**

| Metric | Mean | Median | Min | Max |
|---|---|---|---|---|
| Combined | 34.4% | **33.2%** | 21.6% | 48.5% |
| Cash | 55.8% | 53.9% | 46.7% | 67.2% |
| E-float | 26.2% | 19.9% | 11.1% | 48.9% |

ML has 108–261 fewer shortage events per seed.

* `seasonal_requirement_7d` was the best simple baseline in **every** seed, ahead of yesterday and
  same-weekday.
* The secondary continuous window gives the same ranking in every seed.
* The full-day oracle (evaluation only, impossible operationally) removes 96–100% of unmet demand.

## D. Forecast accuracy (held-out, P50 MAE in BDT)

| Seed | Cash: ML / seasonal 7d / yesterday | Cash vs best | E-float: ML / seasonal 7d / yesterday | E-float vs best | P90 cov. cash / e-float |
|---|---|---|---|---|---|
| 2031 | 9,337 / 10,365 / 13,441 | −9.9% | 11,207 / 11,923 / 14,047 | −6.0% | 85.0% / 89.4% |
| 2032 | 8,906 / 9,875 / 12,627 | −9.8% | 14,570 / 15,820 / 19,134 | −7.9% | 85.1% / 88.1% |
| 2033 | 8,847 / 9,872 / 12,683 | −10.4% | 13,320 / 13,810 / 16,025 | −3.5% | 86.2% / 88.0% |
| 2034 | 8,414 / 9,089 / 11,451 | −7.4% | 11,858 / 12,861 / 14,901 | −7.8% | 84.7% / 88.7% |
| 2035 | 9,942 / 10,989 / 14,372 | −9.5% | 13,116 / 13,922 / 15,693 | −5.8% | 85.5% / 88.8% |

* ML beats naive yesterday by 26–31% on cash and 16–24% on e-float.
* **Pooled P90 coverage:** cash **85.3%**, e-float **88.6%** (nominal 90%).
* **Group detail (seed 2031):**
  * ML beats seasonal 7d in every cluster and segment, except **rural e-float** (MAE 1,749 vs 1,245).
  * Cash P90 coverage is lowest for high-volume agents (80.6%).

**Drivers** (permutation importance on held-out rows; these describe the model, not causes):
* **Cash model:** the 7-day mean requirement dominates, followed by market-day-today, the
  same-weekday mean, previous-day cash-out, and the calendar (day of month and weekday).
* **E-float model:** the 7-day mean requirement dominates, followed by location cluster, day of
  month, the 7-day mean cash-in and the same-weekday mean.

The model predicts the resource requirement for the same operational horizon that the morning
allocation must cover. The gain over seasonal 7d comes from adjusting that history for calendar,
market-day and agent context.

## E. Pre-registered success bar — **PASS**

| Criterion | Required | Observed |
|---|---|---|
| A. ML ≤ seasonal 7d combined unmet | ≥ 4 of 5 seeds | **5 of 5** |
| B. Median incremental reduction | ≥ 5% | **33.2%** |
| C. Seeds where a side is worsened by > 5% | ≤ 1 | **0** |
| D. Exact conservation, every policy and world | yes | **yes** (max district difference BDT 0) |
| E. Pooled P90 coverage in [85%, 95%] | both | cash **85.3%**, e-float **88.6%** |

## F. Harm and group comparison (each policy vs status quo)

| Seed | Seasonal 7d: better / worse | Seasonal 7d: harm BDT | ML: better / worse | ML: harm BDT | ML vs seasonal: better / worse |
|---|---|---|---|---|---|
| 2031 | 121 / 27 | 1,75,734 | 122 / 23 | 1,85,487 | 107 / 25 |
| 2032 | 112 / 36 | 3,05,013 | 118 / 36 | **7,85,065** | 94 / 44 |
| 2033 | 108 / 37 | 3,37,424 | 118 / 39 | **7,78,275** | 89 / 43 |
| 2034 | 110 / 34 | 2,49,598 | 119 / 26 | 2,72,866 | 101 / 23 |
| 2035 | 102 / 46 | 3,54,050 | 104 / 46 | **7,45,913** | 99 / 43 |

**Group shifts in seed 2031** (allocation ratio cash / e-float, and combined unmet change):

| Cluster | Seasonal 7d | ML |
|---|---|---|
| rural | 1.17 / 0.86, −56.7% | 1.26 / **0.69**, −80.0% |
| urban_core | 0.80 / 1.12, −65.7% | 0.73 / 1.15, −78.8% |
| urban_periphery | 1.00 / 0.97, −37.7% | 0.96 / 1.06, −66.3% |

* No group ratio leaves [0.5, 2.0].
* The worst-harmed agents under ML are mostly **high-volume urban-periphery** agents. The largest
  single case is AG-0175 in seed 2031, at +BDT 54,512.

## Caveats that matter for any integration

1. **Signal quantile confound (important).** The ML policy allocates on a **P90** forecast, while
   `seasonal_requirement_7d` is a **mean**.
   * Part of the gain may come from cautious upper-quantile stocking rather than from ML accuracy.
     The P50 accuracy edge is moderate: cash 7–10% and e-float 3.5–8% lower MAE.
   * A non-ML upper-quantile baseline, such as the 7-day max requirement, was **not** pre-registered.
     It should be tested, pre-registered, before claiming how much of the gain is due to ML. Phase
     2D's 6-hour P90 still lost to the seasonal mean, so the quantile alone is not the whole story.
2. **Cash P90 calibration is marginal.** Pooled coverage of 85.3% passes the 85% floor by 0.3 points.
   High-volume agents are about 81%.
3. **Concentrated harm.** In 3 of 5 seeds, ML's total harm (BDT 7.5–7.9 lakh) is more than double
   seasonal 7d's, although ML's total benefit is larger still. Harmed agents must be shown for human
   review.
4. **Rural e-float.** ML gives rural agents 0.69× their status-quo e-float, and the rural e-float
   forecast is worse than seasonal 7d. Rural combined unmet still falls by 80%.
5. **Synthetic world only:**
   * the morning repositioning is assumed instantaneous and free;
   * within-hour net settlement is optimistic;
   * a single world family is used.

## Follow-up (Phase 2F)

Caveat 1, the quantile confound, was tested on fresh seeds 2036–2040. The frozen ML still beat
non-ML q90_7d and max7 baselines in 5 of 5 seeds; see
[QUANTILE_ATTRIBUTION_RESULTS.md](QUANTILE_ATTRIBUTION_RESULTS.md).

## Recommendation

**Fresh confirmatory evidence demonstrates ML value — integrate a human-reviewed Morning Liquidity
Plan into AgentFlow.** Integrate it as decision support on synthetic data only, with three
conditions:
* show harmed agents and group shifts;
* present the P90 coverage caveat;
* pre-register a non-ML upper-quantile baseline check (caveat 1) before any public claim that ML,
  rather than cautious quantile stocking, explains the gain.

The decision to change `main` remains yours.
