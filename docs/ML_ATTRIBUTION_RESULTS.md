# Prepositioning ML Attribution Baseline Audit — Results (Phase 2D)

> **Research only.** Branch `research/prepositioning-ml-attribution`; not merged and not deployed.
> **Synthetic held-out simulation, Dual-Liquidity World v2 (assumptions 2A.1).** No real money
> moved. These results say nothing about real upay performance.

* **Protocol:** [ML_ATTRIBUTION_PROTOCOL.md](ML_ATTRIBUTION_PROTOCOL.md), committed and pushed in
  `047b733` before the comparison ran.
* **Entry point:** `python ml/scripts/run_ml_attribution.py`.
* **Artifacts:** `ml/artifacts_dual/ml_attribution_seed_2026.json` and
  `ml_attribution_multiseed.json`. A second full run reproduced both byte-for-byte.
* **Earlier artifacts:** none were overwritten. Seed 2026 regenerated the Phase 2A artifacts
  exactly.
* **Comparability:** in every seed, the ML policy reproduces the Phase 2C result exactly
  (`ml_matches_phase_2c: true`). The status-quo replay reproduces the world's recorded unmet demand
  exactly. All policies share the same budgets, floors, allocator code and requested flows.

## Verdict

**Pre-registered ML-value bar: FAIL.**

| Check | Required | Observed |
|---|---|---|
| ML combined unmet ≤ best simple baseline | ≥ 4 of 5 seeds | **0 of 5** |
| Median incremental combined-unmet reduction vs best simple | ≥ 5% | **−30.7%** (ML is worse) |
| Exact conservation, every policy and seed | yes | **yes** |
| Seeds where ML raises cash or e-float unmet by > 5% vs best simple | ≤ 1 | **5** (always e-float) |

The best simple baseline is `seasonal_requirement_7d` in **every** seed. It is a non-ML,
need-first allocation from the previous 7 days' realised full-day peak requirements. **Simple
historical allocation explains all of the Phase 2C gain and more.** The current 6-hour ML forecast
is **not yet justified** for a Morning Liquidity Plan.

## A. Seed 2026 — all policies (window 08-18 08:00 → 08-31 23:00, 65,600 agent-hours)

| | Status quo | History-proportional | **Seasonal requirement 7d** | AgentFlow ML (6h P90) | Oracle 6h* | Oracle full day* |
|---|---|---|---|---|---|---|
| Cash shortage events | 1,005 | 543 | 351 | **208** | — | — |
| Unmet cash-out BDT | 37,51,880 | 24,41,745 | 14,62,236 | **9,79,795** | 3,66,826 | 0 |
| Cash-out fill rate | 98.97% | 99.33% | 99.60% | **99.73%** | — | — |
| E-float shortage events | 1,267 | 1,077 | **641** | 1,045 | — | — |
| Unmet cash-in BDT | 46,27,190 | 38,53,613 | **23,45,046** | 37,45,361 | 39,41,091 | 0 |
| Cash-in fill rate | 98.84% | 99.03% | **99.41%** | 99.06% | — | — |
| **Combined unmet BDT** | 83,79,070 | 62,95,358 | **38,07,282** | 47,25,156 | 43,07,917 | 0 |
| Combined fill rate | 98.90% | 99.18% | **99.50%** | 99.38% | — | — |
| Total shortage events | 2,272 | 1,620 | **992** | 1,253 | — | — |
| Fully serviceable agent-hours | 63,328 | 63,980 | **64,608** | 64,347 | — | — |
| Agents with any shortage | 139 | 138 | 128 | **106** | — | — |
| Combined unmet vs status quo | — | −24.9% | **−54.6%** | −43.6% | −48.6% | −100% |
| Agents better / worse vs status quo | — | 106 / 56 | 114 / 36 | 109 / 32 | 117 / 22 | 139 / 0 |

\*ORACLE — evaluation only, impossible operationally.

## B. All five seeds (combined unmet BDT)

| Seed | Status quo | History-prop. | Seasonal 7d (best simple) | AgentFlow ML | ML vs best: combined | ML vs best: cash | ML vs best: e-float | ML vs best: shortage events |
|---|---|---|---|---|---|---|---|---|
| 2026 | 83,79,070 | 62,95,358 | **38,07,282** | 47,25,156 | **−24.1%** | +33.0% | −59.7% | +261 |
| 2027 | 93,33,710 | 69,49,962 | **45,92,493** | 63,60,399 | **−38.5%** | +31.6% | −58.1% | +445 |
| 2028 | 79,40,250 | 60,33,193 | **36,81,525** | 46,76,626 | **−27.0%** | +46.6% | −75.9% | +230 |
| 2029 | 71,76,870 | 55,94,726 | **35,90,414** | 49,48,176 | **−37.8%** | +26.0% | −79.4% | +385 |
| 2030 | 82,76,340 | 74,40,663 | **40,85,925** | 53,39,835 | **−30.7%** | +46.4% | −60.6% | +322 |

Positive percentages mean ML is better; negative means ML is worse.

**Reduction versus the status quo:**

| Policy | Range across seeds | Median |
|---|---|---|
| Seasonal 7d | −50.0% to −54.6% | −50.8% |
| AgentFlow ML | −31.1% to −43.6% | −35.5% |
| History-proportional | −10.1% to −25.5% | — |

## C. ML incremental value against the best simple baseline

| Metric | Mean | Median | Min | Max |
|---|---|---|---|---|
| Combined unmet reduction | −31.6% | −30.7% | −38.5% | −24.1% |
| Cash unmet reduction | **+36.7%** | +33.0% | +26.0% | +46.6% |
| E-float unmet reduction | −66.7% | −60.6% | −79.4% | −58.1% |
| Shortage events (ML − best) | +328.6 | +322 | +230 | +445 |

**Agents, ML compared with the best simple baseline** (better / worse / unchanged):

| Seed | Better | Worse | Unchanged |
|---|---|---|---|
| 2026 | 86 | 56 | 58 |
| 2027 | 75 | 64 | 61 |
| 2028 | 78 | 62 | 60 |
| 2029 | 68 | 64 | 68 |
| 2030 | 62 | 75 | 63 |

**Interpretation.** The ML signal is **better for cash** (26–47% less unmet cash-out than seasonal
7d), because cash pressure falls within the 6-hour morning horizon. It is **much worse for e-float**
(58–79% more unmet cash-in), because e-float pressure peaks in the evening, outside the 6-hour
horizon, while the 7-day full-day history captures it. This matches the Phase 2C oracle
decomposition, where the horizon cost about 57 points.

## D. Pre-registered bar

**FAIL**: 0 of 5 seeds not worse, median −30.7%, and the side check fails in 5 seeds. Conservation is
exact. Per protocol, nothing was tuned.

## E. Harmed agents (seed 2026)

| Group (vs status quo) | Seasonal 7d: unmet change / harmed | AgentFlow ML: unmet change / harmed |
|---|---|---|
| rural (79 agents) | −62.1% / 7 | −75.3% / 1 |
| urban_core (62) | −60.7% / 12 | −37.4% / 6 |
| **urban_periphery (59)** | **−39.6% / 17** | **−6.1% / 25** |
| low volume (71) | −67.4% / 11 | −77.5% / 4 |
| medium volume (80) | −60.9% / 17 | −51.5% / 13 |
| high volume (49) | −44.2% / 8 | −23.1% / 15 |
| **urban_periphery, high volume (23)** | **−37.4% / 4 harmed** | **−5.4% / 12 harmed** |

**The five agents ML harmed most in Phase 2C**, as change in combined unmet versus the status quo:

| Agent | Seasonal 7d (BDT) | AgentFlow ML (BDT) |
|---|---|---|
| AG-0082 | +23,140 | +21,293 |
| AG-0144 | −17,285 | +20,568 |
| AG-0149 | −33,577 | +15,708 |
| AG-0012 | +661 | +15,056 |
| AG-0005 | +24,330 | +13,871 |

Seasonal 7d helps two of these five agents and largely resolves the high-volume urban-periphery
harm. It still harms 36 agents overall, and it moves e-float away from rural agents (e-float ratio
0.80), although rural unmet still falls by 62%.

Allocation ratios (seed 2026):

| Group | Seasonal cash / e-float | ML cash / e-float |
|---|---|---|
| rural | 1.21 / 0.80 | 1.21 / 0.99 |
| urban_core | 0.81 / 1.11 | 0.79 / 1.03 |
| urban_periphery | 1.01 / 0.98 | 1.02 / 0.96 |

## F. Exact resource conservation

Allocations are in whole BDT. For **all six policies** (four operational, two oracles), **all five
seeds**, all 14 held-out days and all 8 districts:
* allocated cash = the status-quo district cash budget;
* allocated e-float = the status-quo district e-float budget.

The maximum absolute district difference is **BDT 0**. Seed 2026 holds BDT 1,55,07,000 cash and
BDT 1,53,20,500 e-float every day. No floor edge case occurred, and no allocation fell below
BDT 5,000.

## Implications (not tested here)

These are hypotheses for future work. Each would need its own pre-registration; none was run or
tuned here.
* **A longer-horizon ML forecast.** A full-day requirement forecast is the obvious candidate,
  because the full-day oracle removes about 100% of unmet demand.
* **A hybrid signal.** ML for cash with seasonal history for e-float. Per-side results suggest it,
  but it was **not** pre-registered and choosing it now would be selection on held-out results.
* **The non-ML seasonal plan itself.** On its own it beat the status quo in every seed (−50% to
  −55% combined unmet) with exact conservation. It could be a credible, simpler Morning Liquidity
  Plan candidate, but it would need its own pre-registered evaluation before any product decision.

## Follow-up (Phase 2E)

The longer-horizon model was evaluated on fresh confirmatory worlds. A full-day ML forecast beat
`seasonal_requirement_7d` in 5 of 5 seeds; see [FULL_DAY_ML_RESULTS.md](FULL_DAY_ML_RESULTS.md).
The recommendation below applies to the **6-hour** ML signal only.

## Recommendation

**Simple historical allocation explains most/all of the gain — do not ship the current ML Morning
Liquidity Plan; evaluate a longer-horizon ML model.**
