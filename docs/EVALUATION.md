# Evaluation — AgentFlow AI

> **Synthetic held-out evaluation.** All numbers come from `python ml/scripts/evaluate.py`
> (machine-readable: `ml/artifacts/metrics.json`, `ml/artifacts/impact.json`). They are
> results on synthetic data, **not** measured real-world upay results. A fresh clone reproduces
> both files byte-for-byte.

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
**identical exogenous customer demand** under three policies:

1. **Without AgentFlow (status quo)** — manual 08:00 drawer reset only. The replay reproduces the
   historical simulation exactly (tested), which validates the simulator.
2. **Rebalancing with naive forecast** — the same risk + rebalancing engine, fed by the seasonal baseline.
3. **With AgentFlow** — ML forecast → risk → rebalancing.

Assumptions: decisions at 09, 11, 13, 15, 17, 19 h; approved transfers arrive 1 hour later;
peer-to-peer only (same district, ≤ 15 km, donor keeps ≥ 110% of its P90 requirement), so the
**total cash in the network is identical across policies**; agents with unusual activity are held
for manual review; every simulated transfer stands in for a human-approved action.

| Metric | Without AgentFlow | Naive-forecast rebalancing | **With AgentFlow** |
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

Trade-offs reported honestly: AgentFlow makes more transfers, about one in five would not have been
strictly needed, and donors are not perfectly safe (25 donor shortage events across 501 transfers,
caused by forecast error on the donor side). The number of agents with *at least one* shortage does
not fall; AgentFlow reduces frequency and severity, not the existence of stress.

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

## 6. Fairness / consistency across operational groups

No personal or sensitive attributes exist; groups are synthetic operational segments.

| Location cluster | Forecast WAPE ML / naive | Alert precision | Alert recall | Shortage prevalence | Unmet demand without → with AgentFlow |
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
* E-float is tracked but not used as a binding constraint.
* The peak-requirement model improves on the seasonal baseline only modestly (−6.8% MAE).
* Anomaly labels are injected patterns; detection performance on real behaviour is unknown.

## Reproduce

```bash
pip install -r requirements.txt
python ml/scripts/run_pipeline.py   # generate -> train -> evaluate (~1 min on 4 cores)
python -m pytest -q                 # 49 tests
```
