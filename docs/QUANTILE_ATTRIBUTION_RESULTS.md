# Cautious Non-ML Baseline Attribution Audit — Results (Phase 2F)

> **Research only.** Branch `research/full-day-ml-quantile-attribution`; not merged and not deployed.
> This is a synthetic held-out simulation on **fresh seeds from the same Dual-Liquidity World v2
> family** (assumptions 2A.1). It is **not** external or real-world validation, and no real money
> moved.

## Timeline (signed and pushed in this order)

| Commit | Step |
|---|---|
| `c01c79f` | Protocol pre-registered ([QUANTILE_ATTRIBUTION_PROTOCOL.md](QUANTILE_ATTRIBUTION_PROTOCOL.md)). |
| `f2840f3` | **Implementation freeze**, before any seed 2036–2040 was generated. |
| (results commit) | One-time evaluation. A determinism rerun with identical code, config and seeds reproduced both artifacts byte-for-byte. |

**Frozen ML.** The ML is exactly the specification of `3128176`. The SHA-256 hashes of all frozen
source files match, and the runner first reproduced the Phase 2E seed-2031 result **exactly**:

| Check | Value |
|---|---|
| ML combined unmet | BDT 16,97,295 |
| mean7 combined unmet | BDT 32,96,539 |
| ML P50 MAE, cash / e-float | 9,337 / 11,207 |

## Verdict

**Pre-registered attribution bar: PASS.** In fresh synthetic worlds, the frozen full-day ML policy
improved on strong historical mean, upper-quantile and maximum baselines under the same working
capital constraints.

| Criterion | Required | Observed |
|---|---|---|
| A. ML ≤ q90_7d combined unmet | ≥ 4 of 5 | **5 of 5** |
| B. ML ≤ max7 combined unmet | ≥ 4 of 5 | **5 of 5** |
| C. Median incremental vs best cautious | ≥ 5% | **20.6%** |
| D. Seeds where a side is worsened by > 5% vs best cautious | ≤ 1 | **0** |
| E. Exact conservation, every policy and seed | yes | **yes** (max district difference BDT 0) |

## A. Each seed — combined unmet BDT (primary window: operating hours, 14 held-out days)

| Seed | Status quo | Mean7 | **Q90_7d** | Max7 | **Frozen ML** | Best cautious | ML vs best |
|---|---|---|---|---|---|---|---|
| 2036 | 1,07,16,360 | 56,42,762 | 49,70,137 | 55,79,975 | **40,82,646** | q90_7d | **−17.9%** |
| 2037 | 70,87,670 | 37,63,955 | 32,88,245 | 33,50,832 | **23,09,973** | q90_7d | **−29.8%** |
| 2038 | 83,64,910 | 47,02,127 | 41,72,543 | 45,21,610 | **33,14,940** | q90_7d | **−20.6%** |
| 2039 | 82,30,760 | 45,18,197 | 38,54,603 | 42,76,719 | **29,55,957** | q90_7d | **−23.3%** |
| 2040 | 87,01,580 | 44,02,356 | 37,37,427 | 38,71,309 | **32,27,040** | q90_7d | **−13.7%** |

* `seasonal_requirement_q90_7d` is the best cautious non-ML baseline in every seed.
* Every cautious baseline beats mean7, which confirms that cautious stocking alone helps.
* ML still beats all of them.
* The secondary continuous window gives the same ordering in every seed.

## B. Cash and e-float separately (ML vs best cautious)

| Seed | Cash unmet: q90 → ML | Cash change | E-float unmet: q90 → ML | E-float change | Shortage events: q90 → ML |
|---|---|---|---|---|---|
| 2036 | 12,53,339 → 7,03,336 | −43.9% | 37,16,798 → 33,79,310 | −9.1% | 640 → 584 |
| 2037 | 15,95,391 → 10,14,082 | −36.4% | 16,92,854 → 12,95,891 | −23.4% | 451 → 275 |
| 2038 | 17,07,616 → 10,35,595 | −39.4% | 24,64,927 → 22,79,345 | −7.5% | 522 → 446 |
| 2039 | 8,64,799 → 4,30,837 | −50.2% | 29,89,804 → 25,25,120 | −15.5% | 508 → 386 |
| 2040 | 5,75,774 → 3,72,026 | −35.4% | 31,61,653 → 28,55,014 | −9.7% | 495 → 488 |

## C. ML incremental value versus the best cautious baseline

| Metric | Mean | Median | Min | Max |
|---|---|---|---|---|
| Combined unmet reduction | 21.0% | **20.6%** | 13.7% | 29.8% |
| Cash unmet reduction | 41.0% | 39.4% | 35.4% | 50.2% |
| E-float unmet reduction | 13.1% | 9.7% | 7.5% | 23.4% |
| Shortage events (ML − best) | −87.4 | −76 | −176 | −7 |

The gain is concentrated on **cash**. The e-float gain is real but smaller (7.5–23.4%).

## D. Coverage of the actual full-day requirement (descriptive; no recalibration)

| Signal | Cash coverage (range across seeds) | E-float coverage |
|---|---|---|
| Mean7 | 52–54% | 57–61% |
| Q90_7d | 79.5–80.6% | 77.6–80.0% |
| Max7 | 85.3–87.2% | 83.4–85.7% |
| **Frozen ML P90** | 84.2–86.1% (**pooled 85.2%**) | 86.9–89.6% (**pooled 88.0%**) |

ML P90 coverage is similar to max7, yet ML allocates better than max7 in every seed. The gain is
therefore not explained by being *more cautious*; ML is better at *where* to place the caution. Cash
P90 remains **under-covered** relative to its nominal 90%, as already noted in Phase 2E.

## F. Harm and group comparison

**Agents versus the status quo** (better / worse, total harm in BDT):

| Seed | Q90_7d | Frozen ML |
|---|---|---|
| 2036 | 111 / 53, harm 7,52,836 | 117 / 47, harm 10,02,123 |
| 2037 | 103 / 42, harm 6,46,755 | 115 / 27, harm 4,44,386 |
| 2038 | 106 / 47, harm 5,59,539 | 114 / 37, harm 5,06,182 |
| 2039 | 111 / 50, harm 5,03,347 | 124 / 29, harm 5,47,834 |
| 2040 | 101 / 47, harm 4,64,023 | 113 / 37, harm 4,86,162 |

**ML directly versus the best cautious baseline:**

| Seed | Better / worse / unchanged | Benefit BDT | Harm BDT |
|---|---|---|---|
| 2036 | 99 / 57 / 44 | 15,97,750 | 7,10,259 |
| 2037 | 90 / 34 / 76 | 12,37,687 | 2,59,415 |
| 2038 | 86 / 47 / 67 | 13,97,701 | 5,40,098 |
| 2039 | 98 / 35 / 67 | 15,05,442 | 6,06,796 |
| 2040 | 87 / 46 / 67 | 10,74,945 | 5,64,558 |

**Groups:**

* **Low-volume agents: the historical baseline is safer in 4 of 5 seeds.** Combined unmet for
  low-volume agents under ML versus q90_7d:
  * 2036: **+21.8%** (28 harmed);
  * 2038: **+0.5%** (23 harmed);
  * 2039: **+5.3%** (14 harmed);
  * 2040: **+43.5%** (24 harmed);
  * 2037 is the exception: −50.4%.
* **Rural e-float.** ML gives rural agents **0.55–0.66×** their status-quo e-float, against
  0.63–0.71× under q90_7d. Rural combined unmet is still 41–57% lower than q90_7d. The ML shifts more
  e-float away from rural agents, and that has to be visible in any plan.
* **High-volume urban periphery.** ML is safer than q90_7d in 2038–2040, where 0–1 agents are harmed
  versus q90 and unmet is 23–37% lower. In 2036–2037 their combined unmet is still 15–16% lower, but
  7 and 5 of them are individually harmed versus q90.
* **Worst-harmed agents.** Under ML versus the status quo, these are mostly urban-periphery agents.
  In seed 2036 the largest are AG-0037 (+89,624) and AG-0056 (+87,970). Under q90_7d, AG-0037 is
  also the worst-harmed (+64,329).
* No group allocation ratio fell below 0.5 or rose above 2.0. The closest was rural e-float at 0.55
  in 2036.

## G. Exact conservation

Allocations are in whole BDT. For **all seven policies** (status quo, mean7, q90_7d, max7, frozen ML,
yesterday, oracle), **all five seeds**, all 14 days and all 8 districts:
* allocated cash = the status-quo district cash budget;
* allocated e-float = the status-quo district e-float budget.

The maximum absolute district difference is **BDT 0**.

## Limitations

* The audit seeds come from the **same** synthetic world family and generator, so this is not
  external validation.
* The P90 is not recalibrated: cash coverage is about 85% against a nominal 90%, and lower for
  high-volume agents.
* Harm is concentrated in low-volume agents, and rural e-float is reallocated. Both need
  human-review safeguards.
* Morning repositioning is assumed instantaneous and free; within-hour net settlement is optimistic.

## Final product decision

**ML attribution survived strong cautious historical baselines — proceed to Morning Liquidity Plan
integration.**

Integrate it as **human-reviewed decision support on synthetic data**. The plan should show:
* harmed agents and group shifts, with low-volume agents and rural e-float called out explicitly;
* the cash P90 under-coverage caveat.

It must not be claimed as real-world, production-validated or guaranteed. The decision to change
`main` remains yours.
