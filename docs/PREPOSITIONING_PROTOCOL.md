# Forecast-Guided Dual-Liquidity Prepositioning — Pre-registered Protocol (Phase 2C)

> **Research only.** Branch `research/forecast-guided-prepositioning`. This is not merged and not
> deployed. `main` and production are unchanged. All data is **synthetic** (Dual-Liquidity World v2,
> assumptions 2A.1). Nothing here moves real money; the held-out comparison is a **simulation**.

This protocol was committed and pushed **before** any prepositioning simulation was run. The
constants live in `ml/agentflow/prepositioning.py` (`SEEDS`, `FLOOR_CASH_BDT`, `FLOOR_EFLOAT_BDT`,
`DECISION_HOUR`, `FORECAST_ROW_HOUR`, `BAR`, `CONCENTRATION_FLAG`, `BETTER_WORSE_TOLERANCE_BDT`), and a
test pins them.

## Question

> Can AgentFlow improve service by **pre-positioning the same total district cash and e-float**
> more intelligently before demand occurs, without injecting any additional working capital?

The peer-swap audit (Phase 2B-0) failed 0 of 5 worlds, so no peer cash ↔ e-float optimiser is
built. This phase tests a different mechanism: a better allocation of the **existing** morning
budgets.

## 1. Fixed world, split and models

* **World:** Dual World v2 assumptions **2A.1**, unchanged. Seeds are **2026, 2027, 2028, 2029 and
  2030**. No world parameter is changed after seeing results, and no seed is dropped or added.
* **Split:** unchanged. The held-out test days are 2026-08-18 → 2026-08-31.
* **Forecast models:** the unchanged Phase 2A pipeline, fitted on each world's own training period.
  No new model and no longer horizon is built in this phase.

## 2. Status quo and budgets

The status quo is the existing 08:00 reset: every agent gets its fixed `target_cash` and
`target_efloat`, with no intra-day action. Each day:

```
district_cash_budget   = Σ status-quo target_cash   (district)
district_efloat_budget = Σ status-quo target_efloat (district)
```

These are **hard limits**. AgentFlow allocates **exactly** the same district totals, using integer
BDT so that conservation is exact. It adds no cash, e-float, credit or overdraft.

## 3. Forecast input (information available at 08:00 only)

The allocation for day *d* uses the existing **6-hour P90** cash and e-float requirement forecasts
from the row at **07:00 on day *d*** (end of hour 07). That forecast covers hours 08:00–13:59 and
is the latest information available before the 08:00 reset. Features are flow-based and never
depend on balances, so the forecasts are identical under both policies.

**Pre-stated limitation:** the 6-hour horizon covers only the morning. Evening e-float pressure is
largely outside it. Whether a longer horizon is *required* will be judged from the results and the
oracles below; no longer-horizon model is built here.

## 4. Allocator (transparent, deterministic, per district and per resource)

1. **Floor.** Each agent gets BDT 5,000 of cash and BDT 5,000 of e-float.
   * *Edge case:* if a district budget cannot cover all floors, the whole budget is split in
     proportion to the status-quo targets (largest-remainder integer rounding), and the event is
     counted.
2. **Need.** `need = ceil(max(P90 requirement − floor, 0))`.
3. **Largest need first.** The remaining budget goes to the largest need first; each agent receives
   min(need, remaining). Ties are broken by `agent_id` ascending.
4. **Leftover.** Once every need is covered, the leftover is distributed in proportion to the
   status-quo targets (largest-remainder integer rounding; ties by agent order).

No optimiser is used and no held-out outcome is read. The allocator reads only `agent_id`,
`district`, `target_cash_level`, `target_efloat_level`, `pred_net_requirement_p90_6h` and
`pred_efloat_requirement_p90_6h`.

## 5. Held-out simulation

* Both policies start from the world's recorded status-quo balances at 2026-08-17 23:00.
* They replay the **same requested** hourly cash-out and cash-in flows with the existing
  resource-conserving `serve_hour` rule.
* At 08:00 each held-out day: the status quo resets to fixed targets, and AgentFlow sets that day's
  allocation. There is no intra-day corrective action.
* **Metrics window:** 2026-08-18 08:00 → 2026-08-31 23:00. Before 08:00 on 08-18 the two policies
  are identical.

## 6. Metrics

* **Cash:** shortage events, unmet cash-out BDT, fill rate.
* **E-float:** the same for cash-in.
* **Network:**
  * fully serviceable agent-hours, combined fill rate and agents with any shortage;
  * cash and e-float allocated per day (exact equality is proven).
* **Efficiency:**
  * unmet BDT avoided per **BDT 1M of daily network working capital**
    (= Σ status-quo cash and e-float targets);
  * shortage events avoided;
  * % improvement at zero extra liquidity.
* **Agents better and worse:** per-agent combined (cash + e-float) unmet over the window. An agent is
  better or worse if the change exceeds BDT 1. Harmed agents are always reported.
* **Allocation shifts:**
  * the largest per-agent daily increase and decrease versus the status quo;
  * AgentFlow / status-quo allocation ratios by location cluster, volume segment and district.

  Extreme concentration is flagged if any group's ratio for either resource is **< 0.5 or > 2.0**.
  Agent-days that receive only the floor are counted.
* **Oracles — evaluation only, impossible operationally.** Both use the same allocator, are
  reported separately and are never used by the policy.
  * *6-h oracle:* actual next-6h requirements at 07:00 replace the P90 forecasts. Its gap to the
    policy measures **forecast error**.
  * *Full-day oracle:* the actual peak requirement over the whole replay day (08:00 → 07:59), from
    requested flows. Its gap to the 6-h oracle measures the **horizon limitation**.

## 7. Pre-registered research bar (not a target)

**Per seed**, the seed passes if:
* combined (cash + e-float) unmet BDT does **not increase**;
* **neither** cash nor e-float unmet BDT increases by more than **2%**;
* district and network totals of cash and e-float are **exactly conserved** every day.

**Across the five seeds**, the overall result passes only if:
* at least **4 of 5** seeds pass the per-seed bar;
* at least **4 of 5** seeds **reduce** combined unmet demand;
* the **median combined unmet reduction is at least 5%**;
* conservation is exact in **all** seeds.

If the bar fails, the study **stops**. The allocator is not tuned on held-out results.

## 8. Language

These results apply only to the synthetic world. We make no claim about real upay performance and
none of production readiness. "Prepositioning" is a morning plan for human review, not an automatic
transfer.
