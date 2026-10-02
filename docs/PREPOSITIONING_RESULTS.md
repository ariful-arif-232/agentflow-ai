# Forecast-Guided Dual-Liquidity Prepositioning — Results (Phase 2C)

> **Research only.** Branch `research/forecast-guided-prepositioning`; not merged and not deployed.
> **Synthetic held-out simulation, Dual-Liquidity World v2 (assumptions 2A.1).** No real money
> moved. "Prepositioning" is a morning plan that a person would review, not an automatic transfer.
> These results say nothing about real upay performance.

* **Protocol:** [PREPOSITIONING_PROTOCOL.md](PREPOSITIONING_PROTOCOL.md), committed and pushed in
  `faed11b` before any simulation was run.
* **Entry point:** `python ml/scripts/run_prepositioning.py`.
* **Artifacts:** `ml/artifacts_dual/prepositioning_seed_2026.json` and
  `prepositioning_multiseed.json`.
* **Other artifacts:** no earlier dual-world or complementarity artifact was overwritten. Seed 2026
  regenerated the Phase 2A artifacts exactly. In every seed, the status-quo replay reproduces the
  world's recorded unmet demand exactly, so both policies face the same requested flows.

## Disclosure: an invalid first run (implementation bug, fixed before the valid run)

The first held-out run had a row-ordering bug:
* `allocate_day` returned rows grouped by district;
* the replay indexes agents by `agent_id`;
* so allocations were applied to the **wrong agents**, often in a different district.

The pre-registered exact-conservation check flagged **every seed as non-conserving**. That run
(combined unmet +445% to +615%) is **invalid**, and its artifacts were not committed.

The fix (`09181fb`) does three things:
* returns rows in `agent_id` order;
* adds a runtime alignment assertion;
* adds a regression test.

It changed **no** protocol rule, allocator rule, parameter or input. It was committed and pushed
before the valid run. All numbers below come from the valid run.

## Verdict

**Pre-registered research bar: PASS.**

| Check | Required | Observed |
|---|---|---|
| Seeds passing the per-seed bar | ≥ 4 of 5 | **5 of 5** |
| Seeds reducing combined unmet demand | ≥ 4 of 5 | **5 of 5** |
| Median combined unmet reduction | ≥ 5% | **35.5%** |
| Exact conservation in all seeds | yes | **yes** |

## A. Seed 2026 — exact comparison

Window: 2026-08-18 08:00 → 08-31 23:00 (14 morning plans, 65,600 agent-hours).

| | Status quo (fixed targets) | AgentFlow (forecast-guided) | Change |
|---|---|---|---|
| Cash shortage events | 1,005 | 208 | −79.3% |
| Unmet cash-out BDT | 37,51,880 | 9,79,795 | **−73.9%** |
| Cash-out fill rate | 98.97% | 99.73% | +0.76 pp |
| E-float shortage events | 1,267 | 1,045 | −17.5% |
| Unmet cash-in BDT | 46,27,190 | 37,45,361 | **−19.1%** |
| Cash-in fill rate | 98.84% | 99.06% | +0.22 pp |
| Combined unmet BDT | 83,79,070 | 47,25,156 | **−43.6%** |
| Combined fill rate | 98.90% | 99.38% | +0.48 pp |
| Shortage events (both sides) | 2,272 | 1,253 | −44.9% (1,019 avoided) |
| Fully serviceable agent-hours | 63,328 | 64,347 | +1,019 |
| Agents with any shortage | 139 | 106 | −33 |
| Cash allocated per day (network) | BDT 1,55,07,000 | BDT 1,55,07,000 | **0** |
| E-float allocated per day (network) | BDT 1,53,20,500 | BDT 1,53,20,500 | **0** |

**Efficiency, with zero extra liquidity:**
* BDT 36,53,914 of unmet demand avoided;
* that is **BDT 1,18,528 avoided per BDT 1M of daily network working capital** (BDT 3.08 crore of
  cash plus e-float).

## B. All five seeds

Reductions are relative to the status quo; positive means less unmet demand.

| Seed | Cash unmet | E-float unmet | Combined unmet | Shortage events | Combined fill | Better / worse agents | Conserved | Bar |
|---|---|---|---|---|---|---|---|---|
| 2026 | −73.9% | −19.1% | **−43.6%** | −44.9% | +0.48 pp | 109 / 32 | exact | pass |
| 2027 | −74.9% | −14.1% | **−31.9%** | −35.0% | +0.41 pp | 102 / 43 | exact | pass |
| 2028 | −78.5% | −9.3% | **−41.1%** | −38.8% | +0.43 pp | 109 / 36 | exact | pass |
| 2029 | −60.2% | −14.2% | **−31.1%** | −31.5% | +0.29 pp | 98 / 32 | exact | pass |
| 2030 | −77.2% | −15.3% | **−35.5%** | −29.8% | +0.41 pp | 115 / 43 | exact | pass |

## C. Robustness across seeds

| Metric | Mean | Median | Min | Max |
|---|---|---|---|---|
| Combined unmet reduction | 36.6% | 35.5% | 31.1% | 43.6% |
| Cash unmet reduction | 72.9% | 74.9% | 60.2% | 78.5% |
| E-float unmet reduction | 14.4% | 14.2% | 9.3% | 19.1% |
| Shortage-event reduction | 36.0% | 35.0% | 29.8% | 44.9% |
| Combined fill-rate change | +0.40 pp | +0.41 pp | +0.29 pp | +0.48 pp |
| Unmet avoided per BDT 1M of daily working capital | 99,681 | 1,01,204 | 71,516 | 1,18,528 |
| Agents better | 106.6 | 109 | 98 | 115 |
| Agents worse | 37.2 | 36 | 32 | 43 |

Seed 2026 has the largest combined reduction of the five (43.6% against 31.1–41.1%), so it is
somewhat favourable. The verdict holds for every seed.

## D. Proof of exact conservation

Allocations use integer BDT. For **every** seed, **every** one of the 14 held-out days and **every**
district, the following plans allocate exactly the status-quo district budget for **both** cash and
e-float:
* the AgentFlow plan;
* both oracles;
* the status quo.

The maximum absolute district difference is **BDT 0**, and the network totals are equal. Seed 2026
budgets each day: cash BDT 1,55,07,000 and e-float BDT 1,53,20,500. Per-district budgets are listed
in the artifact.

Inside the replay, transactions only exchange value between an agent's cash and e-float, so network
working capital equals the unchanged daily budget at every hour (tested). **No cash, e-float, credit
or overdraft is added.** No agent ever received an allocation below the BDT 5,000 floors, and no
district hit the floor edge case.

## E. Agents better and worse (seed 2026; harm is not hidden)

| | Agents | Total change in combined unmet |
|---|---|---|
| Better | 109 | −BDT 38,64,382 |
| Worse | 32 | +BDT 2,10,468 |
| Unchanged (within BDT 1) | 59 | — |

**Worst-harmed agents** (all urban_periphery):

| Agent | Segment | Change in combined unmet |
|---|---|---|
| AG-0082 | high | +BDT 21,293 |
| AG-0144 | high | +BDT 20,568 |
| AG-0149 | high | +BDT 15,708 |
| AG-0012 | high | +BDT 15,056 |
| AG-0005 | medium | +BDT 13,871 |

Across seeds, 32–43 agents are made worse. Per-agent daily allocation shifts in seed 2026:
* cash ranges from −88,134 to +1,16,200 BDT;
* e-float ranges from −37,994 to +61,020 BDT.

## F. Operational-group allocation shifts (seed 2026, AgentFlow / status-quo allocation)

| Group | Cash ratio | E-float ratio | Combined unmet change |
|---|---|---|---|
| rural | 1.21 | 0.99 | −75.3% |
| urban_core | 0.79 | 1.03 | −37.4% |
| urban_periphery | 1.02 | 0.96 | **−6.1%** |
| low volume | 1.08 | 1.07 | −77.5% |
| medium volume | 1.04 | 0.99 | −51.5% |
| high volume | 0.95 | 0.99 | −23.1% |

* District ratios are exactly 1.00 by construction.
* **No concentration flag** fired in any seed (all group ratios within [0.5, 2.0]).
* The policy does **not** remove working capital from rural or low-volume agents; they gain it.
* Cash moves mainly away from cash-in-heavy urban-core agents.
* Urban-periphery agents benefit least, and they make up the most-harmed list.

## Oracles — ORACLE, evaluation only, impossible operationally

| | Combined unmet reduction (mean across seeds) |
|---|---|
| AgentFlow (6-h P90 forecasts at 07:00) | 36.6% |
| 6-h oracle (actual next-6h requirements) | 42.5% |
| Full-day oracle (actual peak requirement for the whole day) | 99.6% |

* **Forecast error** costs about **6 points**: AgentFlow reaches about 86% of the 6-h oracle.
* The **6-hour horizon** costs about **57 points**. The morning forecast cannot see evening e-float
  pressure, which is why e-float gains are only 9–19% while cash gains are 60–78%.
* The full-day oracle removes almost all unmet demand. In this world, the existing district budgets
  are almost always *enough*: the shortages are an **allocation and timing** problem, not a
  liquidity-quantity problem.

## Caveats (important before any production step)

1. **The status-quo baseline is deliberately crude.** World v2 sets each agent's static target to a
   *random* fraction (U(0.42, 0.85)) of its expected daily flow. Part of the gain therefore comes
   from correcting random mis-provisioning, which a careful operator might already partly do (for
   example, provisioning in proportion to historical demand). **A non-ML, demand-proportional
   static baseline was not pre-registered or tested.** So this study shows that forecast-guided
   allocation beats the status quo. It does **not** show how much of the gain needs ML rather than
   simple history.
2. **The horizon is the binding limit, especially for e-float.** A longer-horizon (for example
   full-day) requirement forecast is indicated by the oracle gap. It was not built here.
3. **There is harm.** About 18% of agents are made worse, concentrated in high-volume urban-periphery
   agents. A plan for human review must show them.
4. **Idealised operation.** Allocation and repositioning at 08:00 are assumed instantaneous and free,
   with no transport cost, cash-in-transit limit or distributor constraint. Within-hour net
   settlement is optimistic, and there is a single synthetic world family.

## Update from Phase 2D (supersedes the recommendation below)

The pre-registered ML attribution audit ([ML_ATTRIBUTION_RESULTS.md](ML_ATTRIBUTION_RESULTS.md))
found that a **non-ML 7-day seasonal requirement baseline beats this 6-hour ML policy in all five
seeds**. The ML-value bar failed, so the current ML Morning Liquidity Plan should **not** be shipped.
A longer-horizon ML model is the next candidate.

## Recommendation (Phase 2C, superseded)

**Proceed to a production-facing Morning Liquidity Plan.** The pre-registered bar passed in 5 of 5
seeds with exact conservation and no concentration flags. The plan must be framed as human-reviewed
decision support on synthetic data, and three conditions should be met **before anything reaches
`main`**:

1. a pre-registered comparison against a non-ML demand-proportional static allocation, to establish
   how much of the gain the forecasts themselves provide;
2. harmed agents shown alongside the plan;
3. the cash side presented as the main benefit, with e-float gains marked as limited by the 6-hour
   horizon.

The decision to change `main` remains yours.
