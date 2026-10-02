# Evaluation — AgentFlow AI

> **Synthetic held-out evaluation.** All numbers come from `python ml/scripts/evaluate.py`
> (machine-readable: `ml/artifacts/metrics.json`, `ml/artifacts/impact.json`, `ml/artifacts/policy_selection.json`). They are
> results on synthetic data, **not** measured real-world upay results. With the pinned project
> environment, the evaluated decision outputs, business-impact metrics and demo values reproduce.
> Runtime `fit_seconds` metadata is excluded, and tiny cross-machine floating-point variation may
> occur in internal anomaly thresholds.
>
> Sections 1–7 cover the **legacy intraday environment**, where e-float is tracked but is not a
> binding constraint. Section 8 covers the separate Morning Plan environment.

## 1. Dataset and split

| Item | Value |
|---|---|
| Agents / rows | 200 agents × 76 days × 24 h = 364,800 agent-hours |
| Warm-up dropped | first 7 days (lag-168h features incomplete) |
| Training rows | 262,800 (2026-06-24 00:00 → 2026-08-17 17:00) |
| Purge gap | 6 h — no training target window overlaps the test period |
| Held-out test rows | 66,000 (2026-08-18 00:00 → 2026-08-31 17:00, last 14 days) |
| Split type | strictly time-based, no shuffling |

Leakage controls (all automated in `tests/test_data.py`):

* features use only hours `≤ t`; targets use `t+1 … t+6`;
* "same window on previous days" features are the target series shifted by ≥ 24 h, so the
  window ends at `t−18` at the latest;
* a perturbation test multiplies all future values after a cut-off and asserts every feature at
  or before the cut-off is unchanged (while targets do change);
* the dashboard history hides any 6-h "actual" that would not yet be observable at the decision time.

## 2. Forecasting

**Targets (next 6 hours, per agent):**

* `future_6h_cash_demand` — requested cash-out (gross customer cash demand);
* `future_6h_net_cash_demand` — *peak cumulative net cash drain*
  `max(0, max_k Σ_{j≤k}(cash_out − cash_in))`, i.e. the opening cash an agent needs to serve every
  cash-out request in the window. This is the quantity the risk engine compares with the cash balance.

**Baselines** (same held-out rows):

* *Naive* — the same 6-hour window yesterday;
* *Seasonal* — average of the same 6-hour window over the previous 7 days (a strong baseline).

**Model:** `HistGradientBoostingRegressor` (Poisson loss for cash demand, squared error for the
peak requirement, plus a 0.9-quantile model for the uncertainty band); 31 leakage-safe features
(calendar, agent attributes, lags, rolling statistics, same-window history, velocity).

| Target | Model | MAE (BDT) | RMSE (BDT) | WAPE |
|---|---|---:|---:|---:|
| Cash-out demand | Naive (yesterday) | 9,691 | 18,504 | 27.7% |
| | Seasonal 7-day avg | 7,890 | 15,636 | 22.6% |
| | **ML (gradient boosting)** | **6,138** | **11,816** | **17.6%** |
| Peak net requirement | Naive (yesterday) | 6,972 | 14,209 | 51.4% |
| | Seasonal 7-day avg | 5,524 | 11,612 | 40.7% |
| | **ML (gradient boosting)** | **5,147** | **10,138** | **38.0%** |

* Cash demand: **−22.2% MAE / −24.4% RMSE vs. the best baseline** (−36.7% MAE vs. naive).
* Peak net requirement: **−6.8% MAE / −12.7% RMSE vs. the best baseline** (−26.2% MAE vs. naive).
  This target is intrinsically harder (a maximum of a noisy cumulative difference); the
  improvement is real but modest and we report it as such.
* **P90 quantile band:** empirical coverage **89.5%** (nominal 90%), mean band width BDT 7,461.
* WAPE (Σ|error| / Σ actual) is used instead of MAPE because many hourly windows are near zero.

Top drivers (permutation importance, cash-demand model, held-out): same-window 7-day average,
same window yesterday, same window last week, hour of day, 7-day rolling mean, recent cash-in.

## 3. Risk engine as an early-warning system

Question: *does a HIGH/CRITICAL alert at hour t anticipate a real shortage (unmet cash-out) in
t+1 … t+6?* 38,400 held-out decisions (operating hours 08–21), shortage prevalence 9.2%. The same
deterministic risk engine is fed either ML forecasts or naive seasonal forecasts.

| Risk engine fed by | Precision | Recall | ROC-AUC | Alert rate |
|---|---:|---:|---:|---:|
| **ML forecast** | **81.5%** | **41.7%** | **0.935** | 4.7% |
| Naive seasonal forecast | 84.5% | 31.3% | 0.911 | 3.4% |

Observed shortage rate by risk level (ML): LOW 3.7% · MEDIUM 59.5% · HIGH 79.3% · CRITICAL 86.1% —
monotone, i.e. the score is meaningfully ordered. Thresholds were fixed *a priori* and not tuned on
the test period. Because MEDIUM already carries a ~60% shortage rate, an operator wanting higher
recall could act on MEDIUM+ at the cost of more interventions.

## 4. Behavioural anomaly detection

204 injected anomalous agent-hours in the held-out period (prevalence 0.30%).

| Detector | ROC-AUC | Average precision |
|---|---:|---:|
| Isolation Forest only | 0.974 | 0.575 |
| Robust deviation rule only | 0.982 | 0.671 |
| **Hybrid (deployed)** | 0.981 | 0.671 |

* Status thresholds = 99.0th / 99.7th percentiles of training scores.
* WATCH-or-higher: precision 20.0%, recall 81.4%. Unusual-activity flag: precision 52.9%, recall 67.2%.
* Recall by injected type (WATCH+): odd-hour 100%, cash-churn 95%, rapid-burst 84%, large-ticket 32%.
* Honest finding: a simple robust per-feature rule is as strong as the hybrid on this synthetic
  data and better than Isolation Forest alone. We deploy the hybrid to keep sensitivity to unusual
  *combinations*; on real data the comparison must be repeated.

## 5. Held-out business impact simulation

`ml/agentflow/impact.py` replays the 14-day held-out period hour by hour for all 200 agents with
**identical exogenous customer demand** under four policies:

1. **Without AgentFlow (status quo)** — manual 08:00 drawer reset only. The replay reproduces the
   historical simulation exactly (tested), which validates the simulator.
2. **Rebalancing with naive forecast** — the same risk + rebalancing engine, fed by the seasonal baseline.
3. **AgentFlow V1** — ML forecast → risk → rebalancing with the original nearest-donor optimiser.
4. **AgentFlow V2** — the same ML forecast and risk engine with the cost-, uncertainty- and
   safety-aware rebalancing policy described in §5a (the deployed default since this evaluation).

Assumptions: decisions at 09, 11, 13, 15, 17, 19 h; approved transfers arrive 1 hour later;
peer-to-peer only (same district, ≤ 15 km, donor keeps ≥ 110% of its P90 requirement), so the
**total cash in the network is identical across policies**; agents with unusual activity are held
for manual review; every simulated transfer stands in for a human-approved action.

Results for the original policy (V1); V2 is compared in §5a.

| Metric | Without AgentFlow | Naive-forecast rebalancing | **AgentFlow V1** |
|---|---:|---:|---:|
| Shortage events (agent-hours) | 2,017 | 1,483 | **1,255 (−37.8%)** |
| Unmet cash demand | BDT 95.4 lakh | BDT 67.6 lakh | **BDT 58.3 lakh (−38.9%)** |
| Agents with ≥ 1 shortage | 140 | 143 | 140 |
| Service availability | 96.76% | 97.64% | **97.92% (+1.17 pp)** |
| Cash-out demand fill rate | 97.54% | 98.25% | **98.49%** |
| Simulated transfers / value | — | 384 / BDT 57.1 lakh | 501 / BDT 75.6 lakh |
| Unnecessary transfers (recipient would not have run short) | — | 15.1% | 21.4% |
| Donor shortage events within 6 h of giving | — | 65 | 25 |
| Estimated logistics cost | — | BDT 1.22 lakh | BDT 1.58 lakh |

**Unmet demand avoided: BDT 37.1 lakh over 14 days, with zero additional cash** — the gain comes from
moving existing cash to where the forecast says it will be needed. The ML forecast adds value over
the naive forecast inside the same decision engine (unmet demand 58.3 vs 67.6 lakh).

Trade-offs reported honestly: AgentFlow V1 makes more transfers, about one in five would not have been
strictly needed, and donors are not perfectly safe (25 donor shortage events across 501 transfers,
caused by forecast error on the donor side). The number of agents with *at least one* shortage does
not fall; AgentFlow reduces frequency and severity, not the existence of stress.

## 5a. Rebalancing Policy V2 — cost-, uncertainty- and safety-aware

**Why V2 exists.** V1 serves every HIGH/CRITICAL agent from the *nearest* eligible donors and protects
donors with a flat 110% of their P90 requirement. That produced many small multi-leg transfers and
25 donor shortage events. V2 changes the *decision policy only*; the forecasts, the risk formula and
every V1 hard constraint are unchanged (`ml/agentflow/rebalance_v2.py`). V1 remains available and selectable.

**Deterministic V2 logic.**

1. *Recipient target:* cash up to `P50 + λ·(P90 − P50)`.
2. *Dynamic donor reserve*, never weaker than V1:
   `max(BDT 5,000, 1.10·P90, (P90 + u·(P90 − P50)) × (1 + 0.5·clip(velocity − 1, 0, 1)) × (1 + 0.5·clip(history / 0.15, 0, 1)))`.
   Only cash above this reserve can be given, and after the complete plan the donor must still be LOW risk.
3. *Minimum-benefit gate:* a transfer leg is proposed only if it lowers the recipient's risk level, or
   cuts its risk score by ≥ `min_risk_drop` points, or removes ≥ 50% of its P50 expected shortfall.
   Otherwise the need is escalated to distributor replenishment instead of moving a token amount.
4. *Lexicographic donor ranking:* donors that can cover the remaining need alone first (fewer legs);
   then most recipient risk points removed per BDT 100 of logistics cost; then largest donor margin
   above its reserve; then distance.

Each recommendation carries its evidence: expected risk change and shortfall reduction, donor margin
above its dynamic reserve after the plan, and the ranking key. The text explanation is generated from
those numbers.

**How parameters were selected (held-out test period not used).**

| Period | Dates | Use |
|---|---|---|
| Policy-development | data before each validation window (fold A: 128,400 rows to 07-20 17:00; fold B: 195,600 rows to 08-03 17:00) | forecast models re-trained out-of-sample for each fold |
| Policy-validation | fold A 2026-07-21 → 08-03 (contains a salary period), fold B 2026-08-04 → 08-17 | evaluate V1 and 36 V2 configurations |
| Final held-out test | 2026-08-18 → 08-31 | evaluated once, after selection |

Grid: λ ∈ {0.5, 0.75, 1.0}, u ∈ {0.25, 0.5, 1.0}, `min_risk_drop` ∈ {10, 20},
`require_p50_shortfall` ∈ {no, yes}. The fixed selection rule considers a configuration
*feasible* if, across both folds, it retains ≥ 95% of V1's unmet demand avoided and has no more
donor shortage events than V1. Among feasible configurations it chooses the one with the most unmet
demand avoided per BDT 1,000 of logistics cost. 24 of 36 configurations were feasible.
**Selected: λ = 1.0, u = 0.25, min_risk_drop = 20.** `require_p50_shortfall` made no difference,
because HIGH/CRITICAL agents are always below their P50 requirement. The velocity and history
weights (0.5), the 50% shortfall cut and the "donor stays LOW" rule were fixed a priori. Artifact:
`ml/artifacts/policy_selection.json` (`python ml/scripts/select_policy.py`).

On validation (both folds), the selected V2 retained 101.8% of V1's unmet demand avoided with
664 vs 977 transfers, 20 vs 80 donor shortage events and BDT 34,692 vs 24,779 avoided per BDT 1,000
cost. Unnecessary transfers were essentially unchanged (21.8% vs 21.2%).

**Held-out comparison (synthetic held-out simulation).**

| Metric | Without AgentFlow | Naive forecast | AgentFlow V1 | **AgentFlow V2** |
|---|---:|---:|---:|---:|
| Unmet cash demand | BDT 95.4 lakh | BDT 67.6 lakh | BDT 58.3 lakh (−38.9%) | **BDT 56.9 lakh (−40.3%)** |
| Shortage events | 2,017 | 1,483 | 1,255 (−37.8%) | **1,223 (−39.4%)** |
| Service availability | 96.76% | 97.64% | 97.92% | **97.95%** |
| Demand fill rate | 97.54% | 98.25% | 98.49% | **98.53%** |
| Agents with ≥ 1 shortage | 140 | 143 | 140 | **137** |
| Transfers | — | 384 | 501 | **345** |
| Total rebalanced | — | BDT 57.1 lakh | BDT 75.6 lakh | BDT 75.1 lakh |
| Unnecessary transfers | — | 15.1% | **21.4%** (107) | 24.3% (84) |
| Donor shortage events within 6 h | — | 65 | 25 | **14** |
| Estimated logistics cost | — | BDT 1.22 lakh | BDT 1.58 lakh | **BDT 1.15 lakh** |
| Need escalated to distributor (summed over decisions) | — | BDT 46.0 lakh | BDT 70.5 lakh | BDT 69.9 lakh |
| Unmet demand avoided per transfer | — | BDT 7,226 | BDT 7,404 | **BDT 11,148** |
| Unmet demand avoided per BDT 1,000 cost | — | BDT 22,707 | BDT 23,410 | **BDT 33,340** |
| Shortage events avoided per 100 transfers | — | 139.1 | 152.1 | **230.1** |

**Fixed deployment rule.** V2 parameters were selected only on training-period validation folds,
never on the held-out test. The rule and the held-out results were committed together, so this is
not a separately time-stamped pre-registration. V2 becomes the default only if it retains ≥ 95% of V1's unmet
demand avoided, has no more donor shortage events, and is strictly better on at least two of
{unnecessary-transfer %, donor shortage events, unmet demand avoided per BDT 1,000 cost}. Held-out
result: retention 103.7%; donor events 14 vs 25 (better); avoided per BDT 1,000 cost 33,340 vs
23,410 (better); unnecessary-transfer share 24.3% vs 21.4% (**worse**). Two of three are better, so
**V2 is the default** and V1 stays selectable in the dashboard and the API (`policy=v1`).

**Honest reading of the trade-off.**

* V2 does about as much good as V1 (slightly more: −40.3% vs −38.9% unmet demand) with 31% fewer
  transfers, 27% lower logistics cost and 44% fewer donor shortage events.
* V2 did **not** reduce the *share* of unnecessary transfers; it rose from 21.4% to 24.3%. In absolute
  terms there were fewer unnecessary transfers (84 vs 107), because V2 makes fewer, larger transfers.
  The gate filters small, low-benefit legs; it cannot remove forecast false alarms.
* Donor risk is reduced, not eliminated: 14 donor shortage events across 345 transfers.
* By location (unmet demand, status quo → V1 → V2): urban periphery 45.6 → 21.0 → 19.3 lakh;
  urban core 6.0 → 4.7 → 4.5 lakh; **rural 43.8 → 32.6 → 33.1 lakh**, so V2 is slightly worse than
  V1 for rural agents, where donors are sparse and stricter reserves leave less to share.

### Metric definitions

| Metric | Definition |
|---|---|
| Liquidity shortage event | an agent-hour in which at least one requested cash-out could not be served |
| Unmet cash demand | requested cash-out (BDT) not served because the agent lacked cash |
| Service availability | share of operating agent-hours (08:00–21:59) with cash-out demand in which all requested cash-out was served |
| Demand fill rate | served cash-out / requested cash-out |
| Unnecessary transfer | recipient would have had no shortage in the following 6 h under the status quo |
| Donor shortage after transfer | shortage events at a donor in the 6 h after it gave cash |
| Projected service readiness (dashboard) | share of agents whose current cash covers their forecast 6-h peak requirement |
| Need escalated to distributor | sum, over all decision points, of at-risk need peer rebalancing could not cover (the same agent can be counted at several decisions) |
| Unmet demand avoided per transfer / per BDT 1,000 cost | unmet cash demand avoided vs. status quo divided by transfers / by estimated logistics cost in thousands |
| Shortage events avoided per 100 transfers | shortage events avoided vs. status quo per 100 transfers |

## 6. Fairness / consistency across operational groups

No personal or sensitive attributes exist; groups are synthetic operational segments.

| Location cluster | Forecast WAPE ML / naive | Alert precision | Alert recall | Shortage prevalence | Unmet demand without → with AgentFlow V1 |
|---|---|---:|---:|---:|---|
| Rural | 17.1% / 28.5% | 82.6% | 44.7% | 13.2% | 43.8 → 32.6 lakh (−26%) |
| Urban core | 17.5% / 28.1% | 73.8% | 26.4% | 1.4% | 6.0 → 4.7 lakh (−22%) |
| Urban periphery | 18.0% / 26.7% | 80.5% | 39.6% | 13.2% | 45.6 → 21.0 lakh (−54%) |

By volume segment, forecast WAPE is 17.3–18.4% and alert precision 77–84%.

* Forecast quality is consistent across groups.
* Alert recall is lower for urban-core agents, where shortages are rare; rural agents benefit less
  from peer rebalancing than urban-periphery agents because rural donors are sparser and farther
  apart (more need is escalated to the distributor). A real deployment should monitor this so
  rural agents are not systematically under-served.

## 7. Limitations

* Synthetic data with hand-designed patterns; real behaviour (Eid, weather, outages, customer
  substitution between agents) is richer. Results demonstrate the method, not real-world performance.
* Demand is exogenous in the simulator: unserved customers do not retry or move to another agent.
* Transfers are assumed to complete in 1 hour with a simple cost model; real logistics constraints
  (field-officer capacity, security, cash-in-transit rules) are not modelled.
* In this legacy intraday environment, e-float is tracked but is not a binding constraint (cash-in is
  never declined). Only the separate Morning Plan environment (§8) treats e-float as binding.
* The peak-requirement model improves on the seasonal baseline only modestly (−6.8% MAE).
* Anomaly labels are injected patterns; detection performance on real behaviour is unknown.
* Rebalancing V2 parameters were chosen on two 14-day validation folds of the same synthetic world;
  a real deployment would re-select them on real history and monitor drift. V2 did not lower the
  share of unnecessary transfers and is slightly worse than V1 for rural agents.

## 8. Morning Liquidity Plan: research evidence (separate synthetic environment)

These results come from **Dual-Liquidity World v2**, a separate synthetic environment with finite
cash *and* e-float. They must not be combined with the legacy V1/V2 tables above.

For every step, the protocol and success bar were committed before results were computed. The first
two steps used development seeds 2026–2030. For the confirmatory (2031–2035) and audit (2036–2040)
seeds, the protocol and success bar were committed before those seeds were generated.

| Step | Comparison | Result |
|---|---|---|
| Peer cash ↔ e-float swaps | feasibility of safe, local, same-time complementary pairs | **rejected**: 0 of 5 worlds met the bar |
| 6-hour ML morning plan | vs 7-day seasonal full-day history | **rejected**: seasonal history won in 5 of 5 worlds |
| Full-day ML, fresh confirmatory worlds 2031–2035 | vs seasonal 7-day mean | ML better in 5 of 5 (median −33.2%) |
| **Full-day ML, fresh audit worlds 2036–2040** | vs **best cautious rule** (historical 7-day q90; also 7-day max) | **ML better in 5 of 5; median −20.6% combined unmet (13.7–29.8%); cash −39.4%; e-float −9.7%; BDT 0 extra working capital; exact conservation** |

The headline is the last row, against the strongest cautious baseline. Its success bar required:
* ML ≤ the q90 rule and ML ≤ the max rule, each in at least 4 of 5 worlds;
* a median reduction of at least 5% against the better of the two;
* at most 1 world with cash or e-float unmet worse by more than 5%;
* exact conservation.

All five checks passed.

**Absolute example (audit world seed 2036, 14 held-out operating days).** Combined unmet fell from
about BDT 49.7 lakh (q90 rule) to about BDT 40.8 lakh (frozen ML), −17.9% in this world. Cash-out
fill rose from 99.65% to 99.80%.

Pooled P90 coverage is 85.2% for cash and 88.0% for e-float. Low-volume agents did worse than q90 in
4 of 5 audit worlds. **This is synthetic held-out evidence, not measured upay performance, and not an
expected saving for any demo date.** Details: [MORNING_PLAN.md](MORNING_PLAN.md).

## Reproduce

```bash
pip install -r requirements.txt
python ml/scripts/run_pipeline.py   # generate -> train -> select V2 policy (validation folds) -> evaluate (~4 min on 4 cores)
python -m pytest -q                 # 103 tests
```
