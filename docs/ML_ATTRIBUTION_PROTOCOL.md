# Prepositioning ML Attribution Baseline Audit — Pre-registered Protocol (Phase 2D)

> **Research only.** Branch `research/prepositioning-ml-attribution`. This is not merged and not
> deployed. `main` and production are unchanged. All data is **synthetic** (Dual-Liquidity World v2,
> assumptions 2A.1). This is a held-out **simulation**; nothing moves real money.

This protocol was committed and pushed **before** the comparison was run. The constants live in
`ml/agentflow/ml_attribution.py` (`SEEDS`, `OPERATIONAL_POLICIES`, `SIMPLE_BASELINES`,
`ML_POLICY`, `HISTORY_DAYS`, `BAR`), and a test pins them.

## Question

> How much of the Phase 2C morning-prepositioning improvement actually **requires ML**, rather than a
> simple history-based allocation rule?

Phase 2C compared the forecast-guided plan only against a crude status quo, in which each agent's
static target is a *random* fraction of its expected flow. This audit compares it against strong,
simple, **non-ML** baselines.

## 1. Everything fixed except the allocation signal

* **World:** assumptions 2A.1, unchanged. Seeds are **2026, 2027, 2028, 2029 and 2030**, with no
  drops and no additions.
* **Fixed from Phase 2C:**
  * held-out days 2026-08-18 → 08-31;
  * metrics window 08-18 08:00 → 08-31 23:00;
  * the same requested flows, replayed with the resource-conserving `serve_hour` rule and no
    intra-day action.
* **Budgets:** every policy uses the **same district cash budget and the same district e-float
  budget** (the sums of the status-quo targets), with **exact integer conservation**.
* **Floors:** every policy uses the **same BDT 5,000 floors** for cash and e-float.
* **Allocator:** every policy uses the **same allocator code**, `prepositioning.allocate_resource`,
  as described below.
* **Comparability check:** the ML policy must reproduce the Phase 2C results exactly.

## 2. Policies

**Operational policies:**

| Name | Allocation signal (per agent, per district, per resource) | Allocator mode |
|---|---|---|
| `status_quo` | fixed status-quo targets (reference only) | none: targets applied as-is |
| `history_proportional` | mean **requested cash-out** (cash) / **requested cash-in** (e-float) per operational day over the previous **7 complete operational days** | floors, then the remaining budget **in proportion** to the signal (largest-remainder integers). This is `allocate_resource` with zero need and the signal as its proportional weights. |
| `seasonal_requirement_7d` | mean over the previous **7 complete operational days** of the realised **peak cash requirement** `max(0, max cumsum(out − in))` and **peak e-float requirement** `max(0, max cumsum(in − out))` across the operational day, from requested flows | the **same need-first allocator as ML**, with the signal in place of the P90 forecast |
| `agentflow_ml_p90` | the Phase 2C policy, unchanged: next-6h P90 cash and e-float requirement forecasts from the 07:00 row; no retraining or tuning | need-first allocator |

* An **operational day** *d* runs from 08:00 on day *d* to 07:59 on day *d+1*.
* For the morning plan of day *d*, the previous 7 complete operational days are *d−7 … d−1*. All of
  them end no later than 08:00 on day *d*, so they are fully observed at the 08:00 decision (the same
  information time as the ML policy's 07:00 row).
* No baseline uses the generator's hidden expected-demand parameters, any held-out future
  information, or any outcome label.

**Oracles — evaluation only, impossible operationally:**
* `oracle_6h`;
* `oracle_full_day`.

They are defined as in Phase 2C and are **never** used to select or tune anything.

`seasonal_requirement_7d` deliberately uses **full-day** history. If it beats the 6-hour ML signal,
that is evidence that AgentFlow needs a longer-horizon forecast. It is not an unfair baseline.

## 3. Metrics (for every policy)

* **Cash:** shortage events, unmet cash-out BDT, fill rate.
* **E-float:** the same for cash-in.
* **Network:**
  * combined unmet BDT and combined fill rate;
  * total shortage events and fully serviceable agent-hours;
  * agents with any shortage;
  * agents better or worse than the status quo (per-agent combined unmet change beyond BDT 1).
* **Resources:** exact cash and e-float conservation for every day and district.

## 4. Direct ML value

**Best simple baseline (per seed):** whichever of `history_proportional` and
`seasonal_requirement_7d` has the **lower combined unmet demand** in that seed (ties go to
`history_proportional`).

ML's incremental values are measured against it, per seed:
* `incremental_combined_reduction_pct = 100 × (best − ML) / best`, applied to combined unmet;
* the same formula for cash unmet and for e-float unmet;
* the difference in shortage events;
* agents better or worse than under the best simple baseline (per-agent combined unmet, beyond
  BDT 1).

## 5. Pre-registered ML-value bar (fixed now)

AgentFlow ML adds meaningful decision value **only if all four** hold across the five seeds:

1. ML combined unmet is **≤** the best simple baseline in **at least 4 of 5** seeds;
2. the **median** incremental combined-unmet reduction versus the best simple baseline is
   **≥ 5%**;
3. **exact conservation** holds for every policy in every seed;
4. ML raises cash *or* e-float unmet by **more than 5%** relative to the best simple baseline in
   **at most one** seed.

If the bar fails, nothing is tuned. The conclusion will be that **the current 6-hour ML forecast is
not yet justified for a Morning Liquidity Plan**.

## 6. Group and harm analysis

For the best simple baseline and for AgentFlow ML, each relative to the status quo, results are
reported by location cluster and by volume segment:
* allocation ratios;
* combined unmet change;
* harmed-agent counts.

There is also a specific look at the high-volume urban-periphery agents that Phase 2C harmed.
Regressions are reported, not hidden.
