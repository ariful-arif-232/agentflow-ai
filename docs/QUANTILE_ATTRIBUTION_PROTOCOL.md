# Cautious Non-ML Baseline Attribution Audit — Pre-registered Protocol (Phase 2F)

> **Research only.** Branch `research/full-day-ml-quantile-attribution`. This is not merged and not
> deployed. `main` and production are unchanged. All data is **synthetic** (Dual-Liquidity World v2,
> assumptions **2A.1**). The audit seeds are fresh draws **from the same synthetic world family**.
> They are **not** external or real-world validation. Nothing moves real money.

**Execution order** (each step committed and pushed before the next):
1. this protocol;
2. baseline implementation and tests;
3. **implementation freeze**;
4. **only then** generation and evaluation of seeds 2036–2040;
5. an optional identical determinism rerun;
6. results and docs.

The constants live in `ml/agentflow/quantile_attribution.py`, and a test pins them.

## Question

> Does the **frozen** full-day ML P90 plan still add value against **strong, cautious, non-ML
> historical upper-quantile** allocation rules?

In Phase 2E the ML signal was a **P90**, while the comparator was a 7-day **mean**. This audit
removes that confound by giving the non-ML side its own cautious upper-quantile and maximum
signals.

## 1. Seeds

| Role | Seeds | Use in this phase |
|---|---|---|
| Development (already inspected) | 2026–2030 | not used |
| First confirmatory (already inspected) | 2031–2035 | **only** a frozen-ML regression check: seed 2031 must reproduce the Phase 2E ML result exactly. Never part of the Phase 2F claim. |
| **Phase 2F audit** | **2036, 2037, 2038, 2039, 2040** | generated and evaluated once, after the implementation freeze. No seed is dropped or added. |

All three seed sets are disjoint (tested).

## 2. Frozen ML (no change of any kind)

The ML system is exactly the specification frozen in commit
`3128176e23b4a5a2dde883e8dff8a75f21e35540`. That covers:
* `ml/agentflow/full_day.py`: features, targets, horizon and training;
* `forecast._make_model`: the HistGradientBoosting settings;
* the P50 squared-error and P90 0.9-quantile losses;
* the 07:00 cutoff and 08:00 allocation;
* the full-day P90 cash and e-float allocation signal.

New code only *reads* these modules. A test pins the SHA-256 of every frozen source file. The runner
also reproduces the Phase 2E seed-2031 ML result before evaluating any new seed.

## 3. Policies (only the signal differs)

Every operational policy uses the **same** allocator: `ml_attribution.allocate`, mode `need`, which
is the Phase 2C/2D/2E need-first allocator with the same deterministic tie-breaking. It also uses:
* the **same** district cash and e-float budgets (status-quo sums), with exact integer conservation;
* the **same** BDT 5,000 cash and e-float floors;
* the **same** 08:00 allocation;
* the **same** held-out requested flows;
* the **same** replay (`prepositioning.replay`).

"History" always means the **previous 7 complete operating days**. Each operating day is 08:00–23:59,
and its peak requirement is computed exactly as the Phase 2E target from requested flows.

| Policy | Signal per agent and resource |
|---|---|
| `status_quo` | fixed status-quo targets (reference) |
| `seasonal_requirement_mean7` | mean of the previous 7 peak requirements (the existing Phase 2D/2E baseline) |
| `seasonal_requirement_q90_7d` | **empirical 90th percentile** of the previous 7 peak requirements (method below) |
| `seasonal_requirement_max7` | **maximum** of the previous 7 peak requirements |
| `frozen_full_day_ml_p90` | the frozen full-day P90 forecasts |
| `yesterday_requirement` | previous day's peak requirement (context only) |
| `oracle_full_day` | actual full-day requirement. **ORACLE — evaluation only, impossible operationally** |

**Quantile method (frozen).** This is linear interpolation, identical to
`numpy.quantile(x, 0.90, method="linear")`, and implemented and tested directly. Sort the 7 values
x₍₀₎ ≤ … ≤ x₍₆₎ and let h = (7 − 1) × 0.90 = 5.4. Then
`q90 = x₍₅₎ + 0.4 × (x₍₆₎ − x₍₅₎)`.

## 4. Metrics

* **Primary window:** operating hours 08:00–23:59 of the 14 held-out days (2026-08-18 → 08-31), as in
  Phase 2E.
* **Secondary window:** the continuous window from 08-18 08:00, as in Phase 2C/2D.
* **Every policy:**
  * cash and e-float unmet BDT, shortage events and fill rates;
  * combined unmet and combined fill rate;
  * total shortage events, fully serviceable agent-hours and agents with any shortage;
  * exact district cash and e-float conservation.
* **Coverage (descriptive):**
  * empirical coverage of the actual full-day requirement by the mean7, q90_7d and max7 signals;
  * coverage by the frozen ML P90, per seed and pooled.

  **No recalibration.**

## 5. Attribution comparison

**Best cautious non-ML policy (per seed):** whichever of `seasonal_requirement_q90_7d` and
`seasonal_requirement_max7` has the **lower combined unmet** in the primary window (ties go to
q90_7d). Mean7 is reported separately.

ML is measured against it, per seed, as:
* the % reduction in combined, cash and e-float unmet, with `100 × (best − ML) / best`;
* the shortage-event difference;
* agents better, worse or unchanged (per-agent combined unmet, beyond BDT 1).

## 6. Pre-registered success bar (frozen now)

ML attribution is demonstrated **only if all** of the following hold on seeds 2036–2040:

* **A.** ML combined unmet ≤ `seasonal_requirement_q90_7d` in **at least 4 of 5** seeds.
* **B.** ML combined unmet ≤ `seasonal_requirement_max7` in **at least 4 of 5** seeds.
* **C.** The **median** incremental combined-unmet reduction versus the best cautious baseline is
  **≥ 5%**.
* **D.** ML worsens cash or e-float unmet by **more than 5%** versus the best cautious baseline in
  **at most 1** seed.
* **E.** **Exact** cash and e-float conservation holds for every policy in every seed.

The bar is not changed after results are seen, and the ML is not tuned if it fails.

**Permitted claim if it passes:** *"In fresh synthetic worlds, the frozen full-day ML policy improved
on strong historical mean, upper-quantile and maximum baselines under the same working capital
constraints."* It is not real-world, production or guaranteed evidence.

**Conclusion if it fails:** *"The full-day ML forecast is predictive, but the Morning Liquidity Plan's
operational gain is not clearly attributable to ML beyond a cautious historical allocation rule."*

## 7. Harm and group analysis

The best cautious non-ML policy and the frozen ML are each compared with the status quo, and with
each other. The report covers:
* total benefit and harm in BDT, harmed agents and the worst-harmed agents;
* location cluster and volume segment: allocation ratios, unmet change and harmed counts;
* **high-volume urban-periphery** agents;
* **rural e-float** allocation.

Any group where the historical baseline is safer is reported.
