# Dual-Liquidity Synthetic World v2 (research branch)

> **Research only. NOT deployed and NOT merged into `main`.** This lives on branch
> `feat/dual-liquidity-world-v2`. `main` stays the validated cash-side AgentFlow system, with V1/V2
> results from the legacy world. All data is **synthetic**: no upay data, no real agents, no
> real customers.

## 1. Why a new world

The Phase-1 experiment ([DUAL_LIQUIDITY_EXPERIMENT.md](DUAL_LIQUIDITY_EXPERIMENT.md)) showed that
e-float forecasting is viable. It also showed that the legacy world cannot evaluate e-float
pressure, for three reasons:

* the legacy generator resets e-float every morning to 0.9 × daily **cash-out**, usually more than
  30× the next-6h e-float need;
* it clips e-float at zero and never declines a cash-in, so failed cash-in is not represented;
* its flows are cash-out-dominant in most clusters.

We **refused to change the legacy assumptions to manufacture positive cases**. The legacy world and
its artifacts (`ml/data`, `ml/models`, `ml/artifacts`) remain unchanged. World v2 is a separate,
versioned environment:

| | Legacy world | Dual World v2 |
|---|---|---|
| Code | `ml/agentflow/data_gen.py` | `ml/agentflow/dual_world.py` |
| Data | `ml/data/` | `ml/data_dual/` |
| Models | `ml/models/` | `ml/models_dual/` |
| Artifacts | `ml/artifacts/` | `ml/artifacts_dual/` |
| Entry point | `python ml/scripts/run_pipeline.py` | `python ml/scripts/run_dual_world.py` |
| Used by production API | yes | **no** |

## 2. Dual-resource accounting

An MFS agent manages two coupled resources: physical cash supports cash-out, while e-float supports
cash-in. Each served transaction shifts value from one side to the other.

| Served flow | Agent cash | Agent e-float |
|---|---|---|
| cash-out (customer receives cash) | − served_out | + served_out |
| cash-in (customer deposits cash) | + served_in | − served_in |

```
cash_after   = cash_before   + served_cash_in  − served_cash_out
efloat_after = efloat_before + served_cash_out − served_cash_in
cash >= 0, efloat >= 0 at all times
```

Transactions therefore never create or destroy agent working capital (`Δcash + Δefloat = 0`). The
only other change is the explicit **08:00 status-quo replenishment**, recorded as
`cash_replenishment` and `efloat_replenishment` (positive top-up or negative sweep). Tests check this
hour by hour and over whole sequences.

Every direction distinguishes **requested = served + unmet**:
`requested_cash_out / served_cash_out / unmet_cash_out` and
`requested_cash_in / served_cash_in / unmet_cash_in`. Unlike the legacy world, cash-in can now go
unserved.

## 3. Within-hour service rule (assumption)

The data is hourly, not transaction-sequenced. **Within-hour opposite flows are treated as available
for net settlement; transaction-level ordering is not modelled.** Let C be opening cash, E opening
e-float, O requested cash-out and I requested cash-in:

| Case | Condition | served_out | served_in |
|---|---|---|---|
| Fully feasible | −E ≤ O − I ≤ C | O | I |
| Cash-out dominant | O − I > C | C + I | I |
| Cash-in dominant | I − O > E | O | E + O |

The two dominant cases are mutually exclusive. Each is an upper bound on any feasible plan, so the
rule maximises served BDT under the aggregate within-hour assumption. A test checks it against a
linear-programming solution on 300 random cases.

Hand-calculated test cases:

| Example | Opening cash / e-float (BDT) | Cash-out / cash-in requested (BDT) | Result |
|---|---|---|---|
| A | 10k / 30k | 20k / 15k | Both fully served; ends 5k / 35k |
| B | 5k / 50k | 30k / 10k | Cash-out served 15k (unmet 15k), cash-in served 10k; ends 0 / 55k |
| C | 40k / 5k | 10k / 30k | Cash-out served 10k, cash-in served 15k (unmet 15k); ends 45k / 0 |

Examples D–F cover ample resources, zero flow and multi-hour conservation.

## 4. Pre-registered world rules (fixed before any prevalence or result was computed)

These rules are versioned as `ASSUMPTIONS_VERSION = "2A.1"` in `dual_world.py`. They were committed
before the full world was generated or evaluated, and must not be changed after seeing results.

1. **Calendar and structure are reused from the legacy world:**
   * 200 agents, 76 days, 8 districts;
   * location clusters, volume segments and agent types;
   * hourly profiles and Friday/Saturday weekend;
   * day-level AR(1) regimes and log-normal noise;
   * behavioural anomaly injection.

   World v2 uses its **own seeded random streams** (seed 2026 with stream ids 21–24), so it is
   reproducible and never consumes the legacy stream.
2. **Flow orientation (domestic-remittance corridor).** Urban workers and businesses deposit cash to
   send home (net cash-in); rural households withdraw received remittances (net cash-out). Per-agent
   cash-in/cash-out ratio = cluster median × lognormal(0, 0.15):
   * urban_core 1.25, urban_periphery 1.00, rural 0.70;
   * market stalls × 1.12 (the legacy rule).
3. **Salary and remittance timing.**
   * Urban clusters: the full-strength legacy salary uplift applies to cash-in (wage remittances
     sent); a weak 0.35× uplift applies to cash-out.
   * Rural: the full-strength uplift applies to cash-out, lagged by 2 days (remittances received);
     the weak uplift applies to cash-in.
4. **Market (haat) day.** The legacy all-day cash-out uplift (× 1.45) is kept. Traders deposit
   takings from 14:00 to 19:00 (cash-in × 1.6).
5. **Legitimate local spikes.**
   * About 1 per agent per 10 days (the legacy rate), half cash-out surges and half cash-in surges.
   * × 1.6–2.6 for 2–5 hours between 09:00 and 19:00.
   * Tagged in `flow_event` (`cash_out_surge`, `cash_in_surge`, `haat_trader_deposits`).
   * Kept separate from `known_anomaly_label`: operational stress is not an anomaly or fraud.
6. **Status-quo provisioning (symmetric, same range as legacy cash).** Each morning at 08:00, both
   resources are reset to static targets:
   * `target_cash = expected_daily_cash_out × U(0.42, 0.85)`;
   * `target_efloat = expected_daily_cash_in × U(0.42, 0.85)`;
   * the two fractions are drawn independently on a dedicated stream and rounded to BDT 500.

   The range is the documented legacy cash range. It was **not** chosen to produce any particular
   number of pressure cases.

## 5. Pre-registered evaluation protocol

* **Chronology** is the same as legacy; time is never shuffled.

  | Period | Dates |
  |---|---|
  | Training | 2026-06-17 → targets ending before 2026-08-18 00:00 (6 h purge) |
  | Validation slice (inside training) | 2026-08-04 00:00 → 2026-08-17, purged at the test boundary; models fitted on data before 2026-08-04 minus 6 h |
  | Final held-out test | 2026-08-18 → 2026-08-31 (14 days), evaluated once |

* **Models.** The legacy HistGradientBoosting specs are reused unchanged:
  * cash: point demand, plus P50 and P90 peak net requirement;
  * e-float: P50 and P90 peak net requirement, from the Phase-1 groundwork;
  * P90 ≥ P50 ≥ 0 is enforced.

  Nothing is selected or tuned on the validation slice or the test. The validation slice is
  recorded only.
* **Baselines:** naive same window yesterday, and the 7-day same-window average.
* **Targets** come from requested flows:
  * `future_6h_net_cash_demand = max(0, max_k Σ(out − in))`;
  * `future_6h_net_efloat_demand = max(0, max_k Σ(in − out))`.
* **Decision times:** held-out operating hours 08:00–21:00.
* **Pressure, three ways, for each side and for both sides together:**
  * A. *Forecast requirement pressure:* balance < predicted P50 requirement.
  * B. *Requirement-pressure label:* balance < actual future requirement.
  * C. *Realised events:* unmet > 0 in the current hour, and in the next 6 hours (early warning).
* **Symmetric liquidity state.** Each resource is PRESSURE (balance < P50), WATCH (only the P90 is
  not covered) or COVERED. The two statuses combine into DUAL_PRESSURE / CASH_PRESSURE /
  EFLOAT_PRESSURE / WATCH / HEALTHY. Neither resource is favoured, and no 0–100 combined score is
  invented. The legacy cash risk score is reported alongside for context.
* **Validity bar for Phase 2B.** This is a minimum for being *evaluable*, fixed in advance; it is not
  a target. On held-out decision times, each side must have:
  * realised next-6h unmet-event prevalence ≥ 1%;
  * at least 100 positive decision rows;
  * at least 20 distinct affected agents.

  If either side fails, Phase 2A **stops** and the generator design is revisited scientifically.
  Provisioning will not be adjusted until the bar is met.

## 6. Results — synthetic held-out simulation, Dual-Liquidity World v2

All numbers come from `python ml/scripts/run_dual_world.py`, stored in `ml/artifacts_dual/`. Rerunning
with seed 2026 reproduces `world_summary.json`, `forecast_metrics.json` and `status_quo_impact.json`
byte-for-byte. `training_metadata.json` also records wall-clock fit times, which vary between runs.
World hash: `1e90db46…0bb0231`. The test period was evaluated once, after the rules in §4–5 were
committed (commit `4733645`).

### 6.1 Forecasts (P50 point error; P90 quantile coverage)

**Held-out test (2026-08-18 → 08-31, 66,000 rows):**

| Requirement (next 6 h) | ML MAE | Naive yesterday | Seasonal 7-day | vs best baseline | vs naive | P90 coverage |
|---|---|---|---|---|---|---|
| Cash (`future_6h_net_cash_demand`) | BDT 4,030 | 5,564 | 4,406 | −8.5% | −27.6% | 89.3% |
| E-float (`future_6h_net_efloat_demand`) | BDT 4,638 | 6,116 | 5,010 | −7.4% | −24.2% | 91.1% |

Other held-out metrics:

| Requirement | RMSE | WAPE | Bias | Mean P90 band |
|---|---|---|---|---|
| Cash | 8,720 | 0.395 | −198 | 5,932 |
| E-float | 11,417 | 0.420 | +140 | 7,154 |

**Validation slice** (recorded only, not used for selection):

| Requirement | ML MAE | Seasonal | Naive | P90 coverage |
|---|---|---|---|---|
| Cash | 4,044 | 4,485 | 5,568 | 89.5% |
| E-float | 3,942 | 4,856 | 5,328 | 90.6% |

**Group consistency (held-out):** ML beats both baselines in every cluster and segment, with one
exception: **rural e-float**, where ML (MAE 1,608) only matches the seasonal baseline (1,609). Rural
agents are cash-in-light. Cash P90 coverage per group ranges from 88.0% (rural) to 90.3%.

### 6.2 Pressure at held-out decision times

The evaluation covers 38,400 decisions (operating hours 08:00–21:00). Each cell shows the rate,
then rows / distinct agents.

| | Cash | E-float | Both (dual) |
|---|---|---|---|
| A. Forecast pressure (balance < predicted P50) | 4.72% (1,813 / 83) | 2.30% (884 / 68) | 0 |
| B. Requirement label (balance < actual requirement) | 4.87% (1,871 / 76) | 2.90% (1,113 / 67) | 0 |
| C1. Realised unmet, current hour | 1.94% (744 / 76) | 0.56% (214 / 54) | 0 |
| C2. Realised unmet, next 6 h | 4.87% (1,871 / 76) | 2.90% (1,113 / 67) | 0 |

At decision times, the realised next-6h events (C2) coincide exactly with the requirement label
(B). This is expected when the other resource never binds within the same window: the path of the
binding resource is then exactly `balance ± cumulative requested net flow`.

**Early warning (forecast signal vs realised next-6h unmet):**

| Signal | Cash precision / recall / F1 | E-float precision / recall / F1 |
|---|---|---|
| Expected pressure (P50) | 71.4% / 69.2% / 0.70 | 77.3% / 61.4% / 0.68 |
| Cautious watch (P90) | 51.2% / 89.5% / 0.65 | 45.6% / 84.6% / 0.59 |

**Liquidity-state share at decision times:**

| State | Share |
|---|---|
| HEALTHY | 86.1% |
| WATCH | 6.9% |
| CASH_PRESSURE | 4.7% |
| EFLOAT_PRESSURE | 2.3% |
| DUAL_PRESSURE | 0% |

At the default decision time (2026-08-31 13:00) the counts are: HEALTHY 132, WATCH 28,
CASH_PRESSURE 33, EFLOAT_PRESSURE 7, DUAL_PRESSURE 0.

**Legacy cash risk level by state.** Every EFLOAT_PRESSURE decision has legacy cash risk LOW, so the
legacy score is blind to it. CASH_PRESSURE decisions split LOW 249 / MEDIUM 578 / HIGH 666 /
CRITICAL 320.

### 6.3 Structural finding: per-agent dual pressure is (near) impossible

* **Same-hour dual shortage is impossible by construction.** Under net settlement, a
  cash-out-dominant hour serves all cash-in, and vice versa. This is tested.
* **Within 6 hours it did not occur either.** Transactions conserve an agent's cash + e-float, so
  draining one resource fills the other.
* **Over the 14 days,** only 4 agents had both types of shortage, at different times (28 agents in
  the training period).

So `DUAL_PRESSURE` is not an evaluable per-agent state in this world. This is a property of the
physics, not of tuning. The dual-liquidity problem is a **network** problem: at the same hour, some
agents are short of cash with surplus e-float, while others are short of e-float with surplus cash.
That complementarity is the premise Phase 2B would test. It has **not** been measured yet
(co-location and timing of complementary counterparties).

### 6.4 Status quo (manual 08:00 reset, no rebalancing) — held-out 14 days, 67,200 agent-hours

| | Cash side | E-float side |
|---|---|---|
| Shortage events (agent-hours with unmet > 0) | 1,014 | 1,276 |
| Unmet BDT | 37,55,990 cash-out | 46,28,140 cash-in |
| Requested BDT | 36,65,95,720 | 39,83,64,700 |
| Fill rate | 98.98% | 98.84% |
| Agents with ≥ 1 shortage | 76 | 67 |

Network totals:

* agent-hours fully serviceable on both sides: 64,910 (96.59%);
* dual agent-hours: 0;
* agents with both types over the period: 4;
* total requested BDT 76,49,60,420, served BDT 75,65,76,290;
* combined value fill rate: 98.90%.

The training period shows the same picture: cash events 4,840, e-float events 5,129, and 111 / 106 /
28 agents with cash / e-float / both.

These numbers are **not comparable** to the legacy world's figures (different world).

### 6.5 Validity bar for Phase 2B (pre-registered, §5)

| Side | Next-6h prevalence | Positive rows | Agents | Passes |
|---|---|---|---|---|
| Cash | 4.87% | 1,871 | 76 | yes |
| E-float | 2.90% | 1,113 | 67 | yes |

Both sides are exercised by the pre-specified rules, with no test-set tuning.

## 7. Known limitations

* **Synthetic.** Flow orientation, timing, event and provisioning parameters are documented design
  assumptions, not calibrated to real data. The results show the method in a plausible world, not
  real-world performance.
* **Within-hour net settlement is optimistic.** Real transaction ordering can cause failures that
  hourly netting hides, so unmet demand is likely understated.
* **No demand reaction.** Customers do not retry, defer or switch agents. Requested flows are assumed
  observable, including declined attempts; real systems may not log declined cash-in.
* **Replenishment is idealised.** The 08:00 reset is static, free and unconstrained, with no
  distributor capacity or travel limits.
* **Only one seed has been evaluated so far.** No sensitivity analysis across seeds yet; it would
  need the same fixed rules.
* **Rural e-float forecasting** adds no value over the seasonal baseline.
* **Anomaly detection was not retrained or evaluated** in this world; the labels are carried only.
* **Per-agent DUAL_PRESSURE is not evaluable** (§6.3).

## 8. What real upay validation would require later

* Hourly per-agent cash and e-float balances, including declined cash-out **and** cash-in attempts.
* Replenishment and sweep logs, distributor constraints, and the real geographic flow orientation.
* Re-running the unchanged pipeline with the same chronological split.
* A shadow-mode pilot with operations staff before any decision is acted on.

Only aggregated amounts and counts would be needed, never customer-level data.

## 9. Follow-up: complementarity feasibility audit (Phase 2B-0)

A pre-registered, read-only, five-seed audit asked whether safe, local and simultaneous
complementary counterparties exist for peer cash ↔ e-float swaps.

* Protocol: [DUAL_COMPLEMENTARITY_PROTOCOL.md](DUAL_COMPLEMENTARITY_PROTOCOL.md)
* Results: [DUAL_COMPLEMENTARITY_RESULTS.md](DUAL_COMPLEMENTARITY_RESULTS.md)

**Outcome: 0 of 5 worlds met the minimal bar.** A network V3 optimiser is not supported by this
world.
