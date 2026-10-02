# Dual-Liquidity Complementarity Feasibility Audit — Results (Phase 2B-0)

> **Research only.** Branch `research/dual-complementarity-feasibility`. This is not merged and not
> deployed. All data is **synthetic**: Dual-Liquidity World v2, assumptions 2A.1, unchanged.
> **Label:** synthetic held-out simulation, read-only feasibility audit. No swap was recommended,
> executed or simulated, and no business impact was computed.

* **Protocol:** [DUAL_COMPLEMENTARITY_PROTOCOL.md](DUAL_COMPLEMENTARITY_PROTOCOL.md), committed and
  pushed in `961ef41` before any multi-seed world was generated.
* **Entry point:** `python ml/scripts/run_complementarity.py`.
* **Artifacts:**
  * `ml/artifacts_dual/complementarity_seed_2026.json`;
  * `ml/artifacts_dual/complementarity_multiseed.json`.

  A second full run reproduced both files byte-for-byte.
* **Phase 2A artifacts were not overwritten.** Seed 2026 regenerated them identically
  (`phase_2a_artifacts_reproduced: true`).

Under the Dual World v2 hourly net-settlement model, same-agent simultaneous dual shortage does not
occur. This audit asked whether **network-level** complementarity exists at the same time and in the
same place. **Under the pre-registered definitions, it largely does not.**

## Verdict

**Pre-registered bar: 0 of 5 worlds pass (4 required). Overall: FAIL.** Local complementary
cash ↔ e-float rebalancing is **not sufficiently supported** by the synthetic world. As
pre-registered, the audit stops here. The world assumptions, reserves and rules were not changed.

## Seed 2026 (primary decision cadence, 84 timestamps × 200 agents = 16,800 decisions)

| Metric | Cash side (A needs cash) | E-float side (B needs e-float) |
|---|---|---|
| Pressure decision rows (P50 > balance) | 901 | 373 |
| Eligible rows (NORMAL + own safe surplus) | 762 | 295 |
| Rows with ≥ 1 viable counterparty | 15 (**1.7%**) | 17 (**4.6%**) |
| Distinct participating agents | 7 | 9 |
| Total P50 need (BDT) | 53,09,614 | 82,90,449 |
| Need coverable by greedy allocation | **2.0%** | **1.3%** |

**Pairs:**
* 50 candidate pairs were within 15 km; **19 were viable** (capacity ≥ BDT 2,000).
* Raw viable capacity was BDT 1,14,500, which double-counts donors.
* The greedy feasibility allocation found 15 assignments, **BDT 1,06,000 safely swappable**
  (median assignment BDT 6,000).
* The median viable pair amount was BDT 3,500.
* Distance: median 11.4 km, P90 14.3 km.
* Useful districts (at least 10 viable pairs): **0 of 8**.

**Why counterparties are missing** (first matching reason; each row of pressure rows is counted
once):

| Reason | Cash-pressure rows | E-float-pressure rows |
|---|---|---|
| Has a viable counterparty | 15 | 17 |
| Behaviour not NORMAL | 139 | 78 |
| No own safe surplus | 0 | 0 |
| **No eligible opposite-side agent in the district at that time** | **549** | 95 |
| **Eligible agent exists but none within 15 km** | 174 | **157** |
| Capacity below BDT 2,000 | 24 | 26 |

**By district** (pressure rows cash / e-float, viable pairs, BDT swappable):

| District | Pressure rows (cash / e-float) | Viable pairs | BDT swappable |
|---|---|---|---|
| Barishal | 114 / 34 | 9 | 30,500 |
| Chattogram | 103 / 101 | 1 | 6,000 |
| Dhaka | 87 / 111 | 3 | 2,000 |
| Gazipur | 232 / 22 | 5 | 60,500 |
| Khulna | 32 / 39 | 0 | 0 |
| Rajshahi | 115 / 19 | 1 | 7,000 |
| Rangpur | 108 / 24 | 0 | 0 |
| Sylhet | 110 / 23 | 0 | 0 |

**Hourly appendix (08:00–21:00, descriptive)** — viable pairs per hour, summed over 14 days:

| Hour | Pressure rows (cash / e-float) | Viable pairs |
|---|---|---|
| 08–09 | — | 0 |
| 10–12 | 158–192 / 4–12 | 1–3 per hour |
| 13 | — | 0 |
| 14–17 | 174–209 / 49–128 | 7–14 per hour |
| 18–21 | 23–90 / 134–149 | 0 |

Cash pressure peaks from late morning to afternoon; e-float pressure peaks in the evening. The two
overlap only around 14:00–17:00.

**Oracle (evaluation only; actual future requirements, never used operationally):**
* even with perfect knowledge, only **45 viable pairs** exist;
* 4.3% of cash-side and 8.9% of e-float-side rows have a counterparty;
* BDT 3,26,500 is swappable.

Forecast error is therefore **not** the main limitation; the structure is. Of the 19 operational
viable pairs, 58% were truly complementary in hindsight.

## All five pre-registered seeds

| Seed | Cash prev. (next 6 h) | E-float prev. | Cash fcst vs best | E-float fcst vs best | P90 cov. cash / e-float | Viable pairs | Agents | Cash rows w/ counterparty | E-float rows w/ counterparty | Swappable BDT | Cash need cov. | E-float need cov. | Useful districts | Bar |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2026 | 4.87% | 2.90% | −8.5% | −7.4% | 89.3% / 91.1% | 19 | 16 | 1.7% | 4.6% | 1,06,000 | 2.0% | 1.3% | 0 | ✗ |
| 2027 | 3.84% | 4.02% | −7.6% | −8.4% | 90.3% / 90.2% | 40 | 28 | 2.9% | 7.6% | 1,11,500 | 2.2% | 1.0% | 2 | ✗ |
| 2028 | 4.30% | 2.96% | −7.5% | −8.4% | 89.4% / 90.6% | 31 | 24 | 2.5% | 7.8% | 1,81,500 | 3.0% | 2.5% | 1 | ✗ |
| 2029 | 2.84% | 3.38% | −7.0% | −7.5% | 90.0% / 90.3% | 42 | 31 | 4.9% | 8.7% | 1,85,000 | 6.0% | 2.4% | 1 | ✗ |
| 2030 | 3.32% | 3.88% | −8.4% | −5.6% | 89.8% / 90.6% | 28 | 28 | 3.9% | 5.0% | 1,55,500 | 3.5% | 1.3% | 0 | ✗ |

The forecast columns show the MAE change versus the best baseline (negative = better).

**Bar checks per seed:**
* only the "≥ 20 distinct agents" check passes, in seeds 2027–2030;
* no seed reaches 100 viable pairs (the maximum is 42);
* no seed reaches 10% on either side (the maxima are 4.9% cash and 8.7% e-float).

## Robustness across seeds

| Metric | Mean | Median | Min | Max |
|---|---|---|---|---|
| Viable pairs | 32.0 | 31 | 19 | 42 |
| Distinct agents | 25.4 | 28 | 16 | 31 |
| Cash rows with counterparty | 3.2% | 2.9% | 1.7% | 4.9% |
| E-float rows with counterparty | 6.7% | 7.6% | 4.6% | 8.7% |
| Swappable BDT | 1,47,900 | 1,55,500 | 1,06,000 | 1,85,000 |
| Cash need coverable | 3.4% | 3.0% | 2.0% | 6.0% |
| E-float need coverable | 1.7% | 1.3% | 1.0% | 2.5% |
| Useful districts | 0.8 | 1 | 0 | 2 |
| Cash forecast vs best baseline | −7.8% | −7.6% | −7.0% | −8.5% |
| E-float forecast vs best baseline | −7.5% | −7.5% | −5.6% | −8.4% |
| P90 coverage, cash / e-float | 89.7% / 90.5% | — | 89.3% / 90.2% | 90.3% / 91.1% |

**Is seed 2026 representative?** By the pre-registered rule, seed 2026 is **unusually weak** for
complementarity. It ranks 5th of 5 on five of the six key metrics, below the other seeds' minimum:
* cash share 1.7% vs 2.5–4.9%;
* e-float share 4.6% vs 5.0–8.7%;
* pairs 19 vs 28–42;
* swappable BDT 1.06 vs 1.12–1.85 lakh;
* cash coverage 2.0% vs 2.2–6.0%.

It lies within range on e-float need coverage (rank 3). Even the strongest seed (2029: 42 pairs,
4.9% / 8.7%) fails the bar. The negative verdict does not depend on seed 2026, and the forecast
quality of seed 2026 is typical.

## Interpretation (hypotheses, not claims)

* **Timing.** Pressure is mostly **non-simultaneous**. Cash pressure builds from late morning
  through the afternoon, and e-float pressure in the evening, after a day of deposits.
* **Location.** Pressure is mostly **non-co-located**: the same-district requirement fails for 61%
  of cash-pressure rows. Cash pressure concentrates in cash-out-oriented districts and clusters, and
  e-float pressure in urban, cash-in-oriented ones, often more than 15 km apart.
* **Forecasting is not the bottleneck.** Perfect foresight (the oracle) still finds only 45 pairs.
* **An untested alternative.** Pressure shifts from cash to e-float over the course of the day. If
  the *same* agents swing between the two (not measured here), interventions that act **across time
  for one agent or a distributor** (for example time-aware provisioning) may matter more than
  **peer-to-peer swaps**. This is a hypothesis for a future, separately pre-registered study.

These conclusions hold for this synthetic world only. They do not show that real MFS networks lack
complementary agents, and they make no claim about upay.

## Recommendation

**Do not build V3; complementarity is not sufficiently supported.** Under the pre-registered
definitions, safe, local and simultaneous complementary counterparties are too rare in every seed to
justify a peer cash ↔ e-float network optimiser.
