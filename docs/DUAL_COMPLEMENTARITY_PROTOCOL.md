# Dual-Liquidity Complementarity Feasibility Audit — Pre-registered Protocol (Phase 2B-0)

> **Research only.** Branch `research/dual-complementarity-feasibility`. This is not merged and not
> deployed. `main` and production are unchanged. All data is **synthetic** (Dual-Liquidity World v2).
> This audit is **read-only with respect to operational policy**: it measures whether complementary
> counterparties exist. It does not recommend, execute or simulate swaps, and it does not estimate
> business impact.

This protocol was committed and pushed **before** any multi-seed world was generated and before
any complementarity number was computed. The constants live in `ml/agentflow/complementarity.py`
(`SEEDS`, `DECISION_HOURS`, `MAX_DISTANCE_KM`, `MIN_SWAP_BDT`, `ROUNDING_BDT`, `RESERVE_FLOOR_BDT`,
`RESERVE_MULTIPLIER`, `BAR`, `MIN_WORLDS_PASSING`, `USEFUL_DISTRICT_MIN_PAIRS`), and a test pins them.

## Question

> Does the pre-registered Dual-Liquidity World contain enough **safe, local and simultaneous**
> complementary agent liquidity to justify building a cash ↔ e-float network optimiser?

Under the Dual World v2 hourly net-settlement model, same-agent simultaneous dual shortage does not
occur. The next question is whether network-level complementarity exists at the same time and in the
same place.

## 1. Fixed world and models

* **World:** assumptions version **2A.1**, exactly as committed in Phase 2A. No provisioning, flow
  ratio, event rate or split changes.
* **Seeds:** **2026, 2027, 2028, 2029, 2030**, fixed now. Changing the seed changes stochastic draws
  only. No seed is removed and none is added after results are seen.
* **Forecast models:** the unchanged Phase 2A pipeline and hyper-parameters, fitted on each world's
  own training period.
* **Behavioural status:** the unchanged legacy hybrid anomaly detector, fitted on each world's own
  training period. At a decision time, an agent's status is the worst score in the trailing 6 hours
  (the legacy engine rule). **Only NORMAL agents are eligible**, on both sides.
* **Seed 2026 artifacts:** the Phase 2A artifacts are not overwritten. Seed 2026 is regenerated and
  must reproduce them exactly.

## 2. Decision times

* **Primary view:** held-out test days 2026-08-18 → 2026-08-31 at **09:00, 11:00, 13:00, 15:00,
  17:00 and 19:00**. That is 84 decision timestamps per world, chosen before seeing any result.
* **Appendix:** every operating hour from 08:00 to 21:00, descriptive only.

Operational pairing uses **predictions and current balances only**. No future or label column is
read.

## 3. Audit reserves (not the final V3 policy)

```
cash reserve    = max(BDT 5,000, 1.10 × predicted cash P90 requirement)
e-float reserve = max(BDT 5,000, 1.10 × predicted e-float P90 requirement)
safe cash surplus    = max(cash − cash reserve, 0)
safe e-float surplus = max(e-float − e-float reserve, 0)
```

## 4. Complementary pair

**Agent A, the cash-pressure side**, needs physical cash:
* predicted cash P50 > current cash;
* safe e-float surplus > 0;
* NORMAL behaviour.

**Agent B, the e-float-pressure side**, needs e-float:
* predicted e-float P50 > current e-float;
* safe cash surplus > 0;
* NORMAL behaviour.

A and B must be in the **same district** and **≤ 15 km** apart (haversine distance on the synthetic
coordinates). The physical cash leg needs logistics; the e-float leg is assumed instantaneous for
research purposes.

**Capacity:**

```
A cash need    = max(cash P50 − A cash, 0)
B e-float need = max(e-float P50 − B e-float, 0)
capacity = min(A cash need, B e-float need, A safe e-float surplus, B safe cash surplus)
amount   = capacity rounded DOWN to BDT 500; viable if amount ≥ BDT 2,000
```

A future swap of x would move **x physical cash B → A** and **x e-float A → B**. Network cash and
network e-float are then each unchanged (tested). Nothing is executed: such a swap would remain a
future, human-reviewed recommendation and never an automatic transfer.

## 5. Two analyses

* **A. Candidate-pair availability.** Does at least one viable counterparty exist? Raw pair
  capacities double-count donors, so they are reported only as non-additive.
* **B. Conservative greedy feasibility allocation.** This is an upper-bound feasibility check, not
  V3 and not a policy, with no impact evaluated. At each decision time:
  * agents on both sides are processed in descending order of their own P50 gap (ties broken by
    agent id);
  * each agent tries its valid counterparties nearest first;
  * each assignment is the rounded-down minimum of the remaining needs and surpluses, if it is at
    least BDT 2,000;
  * needs and surpluses are decremented, so each BDT of capacity is used at most once per decision
    time.

## 6. Metrics

For each world:
* decision timestamps;
* cash-pressure and e-float-pressure decision rows, and the eligible rows on each side;
* rows on each side with at least one viable counterparty, and the reasons when none exists:
  * not NORMAL;
  * no safe surplus of its own;
  * no eligible opposite-side agent in the district;
  * none within 15 km;
  * capacity below BDT 2,000;
* distinct participating agents, per side and in total;
* viable pair opportunities;
* total P50 cash need and e-float need;
* greedy safely swappable BDT, and the % of each need it covers;
* median capacity and median greedy assignment;
* median and P90 distance;
* results by district, and the number of **useful districts** (at least 10 viable pair
  opportunities);
* forecast results from the unchanged Phase 2A evaluation: pressure prevalence, improvement over the
  best baseline, and P90 coverage on each side.

An **oracle analysis** is optional and for **evaluation only**. It repeats the pairing with
*actual* future requirements, which also replace the P90s in the reserves. It also reports the share
of operational viable pairs in which both sides really were in requirement pressure. It is never
used operationally.

**Is seed 2026 representative?** The key metrics are:
* share of cash-pressure rows with a counterparty;
* share of e-float-pressure rows with a counterparty;
* viable pairs;
* swappable BDT;
* % of cash need coverable;
* % of e-float need coverable.

Seed 2026 is **typical** if each key metric lies within the [min, max] range of the other four
seeds. It is **unusually strong** (or **weak**) if most key metrics lie above that range's maximum
(or below its minimum). Any other pattern is reported as **mixed**.

## 7. Minimal evaluability bar (not a target)

A world passes if **all** of the following hold over its held-out primary decisions:

| Criterion | Minimum |
|---|---|
| Distinct agents participating in viable complementary opportunities | ≥ 20 |
| Viable complementary pair opportunities | ≥ 100 |
| Cash-pressure decision rows with ≥ 1 viable counterparty | ≥ 10% |
| E-float-pressure decision rows with ≥ 1 viable counterparty | ≥ 10% |

Denominators are **all** pressure rows on that side, including ineligible ones.

**Overall:** at least **4 of 5** worlds must pass. If the bar fails, the audit **stops**, and the
report says that local complementary rebalancing is not sufficiently supported by the synthetic
world. World assumptions are never changed to make it pass.

## 8. Language

We do not claim that dual pressure never exists in real MFS, that every network has complementary
agents, or any real upay saving. We make no prediction of optimiser impact before it is simulated.
