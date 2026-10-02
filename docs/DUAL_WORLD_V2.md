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
