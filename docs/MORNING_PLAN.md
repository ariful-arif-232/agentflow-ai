# Morning Liquidity Plan

> **Synthetic decision support.** The Morning Plan runs on a deterministic synthetic demo fixture.
> It is human-reviewed, it never moves money, and it uses the same working capital as the status quo.
> The research evidence below is **synthetic held-out evidence, not measured upay performance**.

## What it is

AgentFlow works on two operational time scales:

| | When | What | Resources |
|---|---|---|---|
| **Proactive: Morning Plan** | 07:00 forecast → 08:00 positioning | Forecast each agent's **full operating-day** (08:00–23:59) physical-cash and e-float requirement, then propose where the **same** district working capital should sit before demand arrives | cash **and** e-float |
| **Reactive: intraday** | every hour | 6-hour cash risk, explanations and **V2** peer rebalancing when pressure emerges | physical cash |

```
PLAN → PREDICT → EXPLAIN → REBALANCE → HUMAN REVIEW → MEASURE
```

An MFS agent manages two coupled resources: physical cash serves cash-out, and e-float serves cash-in.
Each transaction shifts value from one side to the other. The Morning Plan positions both. V2 stays
cash-only.

## How a plan is made (serving path)

1. **Frozen forecasts.**
   * The fixture holds full-day P50/P90 forecasts from the frozen research model (spec
     `3128176e23b4a5a2dde883e8dff8a75f21e35540`).
   * It covers 14 held-out dates of one synthetic world: Dual-Liquidity World v2, assumptions 2A.1,
     seed 2036.
   * It contains decision-time inputs only: no realised demand, targets, outcomes or oracle values.
2. **Live allocation.** The API recomputes the plan on every request with the validated
   deterministic allocator:
   * each district's cash and e-float budgets stay **exactly** at their status-quo totals (integer
     BDT);
   * every agent keeps a **BDT 5,000** floor of each resource;
   * the remaining budget goes **need-first** by full-day P90 requirement, with ties broken by agent
     ID;
   * anything left after all P90 needs are covered is shared in proportion to status-quo allocations.
3. **Runtime assertions.**
   * Conservation per district and network, floors, non-negativity and the absence of any
     future/outcome field are all checked when the plan is built.
   * The plan matches the frozen research allocation exactly
     (`matches_frozen_research_allocation: true`).
4. **Explanations.** These are fixed templates over the plan's numbers, with no LLM. Example: *"Cash
   increased because the full-day P90 requirement exceeds the current morning allocation while the
   district budget remains fixed."*
5. **Review flags.** These are fixed rules on the plan itself; outcomes are unknown at 07:00.

   | Flag | Rule |
   |---|---|
   | *Large allocation decrease* | a cut of at least 50% and at least BDT 20,000 |
   | *Low-volume review* | a low-volume agent with a cut of at least 25% and at least BDT 5,000 |
   | *Rural e-float review* | a rural agent with an e-float cut of at least 50% |
   | *Below full-day P90 need* | the recommended allocation is below the agent's P90 need |

6. **Human review.** `POST /api/morning-plan/simulate` requires an explicit acknowledgement. It
   records an in-memory audit entry and returns the conservation proof with *"Simulation approved —
   no money moved."*

The API loads only two small JSON files: `ml/artifacts/morning_plan_demo.json` (about 164 KB) and
`ml/artifacts/morning_plan_evidence.json`. It never loads the Dual World dataset, trains a model or
creates a second engine. To regenerate both files exactly, run
`ml/scripts/research/build_morning_plan_fixture.py` against the research checkout `c741804`.

## API

| Endpoint | Purpose |
|---|---|
| `GET /api/morning-plan/dates` | demo dates, default date (2026-08-31), metadata and labels |
| `GET /api/morning-plan?date=YYYY-MM-DD` | network summary, districts with conservation proof, agents (allocations, P50/P90, deltas, coverage, flags, explanations), review focus |
| `GET /api/morning-plan/evidence` | aggregate research evidence and caveats |
| `POST /api/morning-plan/simulate` | human-review simulation only (`date`, `reviewer_acknowledged`, optional `reviewer_note`) |
| `GET /api/morning-plan/audit` | simulated approvals (in memory) |

## Research evidence (historical, synthetic)

> In fresh synthetic worlds from the same pre-registered world family, the frozen full-day ML policy
> reduced combined unmet demand by a median **20.6%** versus the strongest cautious historical
> baseline, while conserving each district's cash and e-float budgets exactly.
>
> **This is synthetic held-out evidence, not measured upay performance.**

| Frozen full-day ML P90 vs best cautious non-ML rule (historical 7-day q90) | Value |
|---|---|
| Fresh audit worlds (seeds 2036–2040) improved | **5 / 5** |
| Median combined unmet reduction (range) | **20.6%** (13.7–29.8%) |
| Median unmet cash-out reduction | 39.4% |
| Median unmet cash-in (e-float) reduction | 9.7% |
| Extra working capital | **BDT 0**, exact conservation |
| Pooled P90 coverage, cash / e-float | 85.2% / 88.0% (nominal 90%) |

The 20.6% figure is **not** an expected saving for any date shown in the demo. The easier comparison
against a 7-day mean (−33.2% in Phase 2E) is deliberately **not** the headline.

## How we got here: negative results kept on purpose

Each research phase was pre-registered, run once on fresh seeds and pushed before results.

1. **Peer cash ↔ e-float swaps were rejected.** Safe, local, same-time complementary counterparties
   were too sparse: 0 of 5 worlds met the bar.
2. **The 6-hour ML was rejected for morning planning.** A non-ML seasonal full-day history baseline
   beat it in 5 of 5 worlds, because the forecast horizon did not match the decision.
3. **The horizon was aligned to the decision.** A full-day ML model beat the seasonal mean in 5 of 5
   fresh confirmatory worlds.
4. **The final attribution survived cautious baselines.** The frozen full-day ML beat the historical
   q90 and max-7-day rules in 5 of 5 fresh worlds.

The full protocols and results live on research branches `research/dual-complementarity-feasibility`,
`research/prepositioning-ml-attribution`, `research/full-day-ml-confirmatory` and
`research/full-day-ml-quantile-attribution`. That last branch is at commit `c741804`.

## Caveats (shown in the product)

* There is a synthetic world family only, with no upay data, no external validation and no
  guaranteed savings.
* Cash P90 coverage is about 85%, below the nominal 90%, so the cautious forecast under-covers cash.
  Coverage is lower still for high-volume agents.
* Low-volume agents did worse than the cautious q90 rule in 4 of 5 synthetic audit worlds.
* Rural e-float allocations can fall materially (about 0.55–0.66× status quo in the audit).
* Morning repositioning is assumed instantaneous and free, and within-hour net settlement is
  optimistic.
* Human review is required. Real-data shadow validation is required before any deployment.

**What not to say:** "proven in real upay operations", "production validated", "guaranteed
savings", "universally better", or "this date will save 20.6%".
