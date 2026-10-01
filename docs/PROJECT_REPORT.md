# AgentFlow AI — Project Report (outline-ready)

**Explainable Predictive Liquidity Orchestration for MFS Agent Networks** · *Predict. Explain. Rebalance.*
AI DEV FEST 2026 AI Hackathon (DIU CPC × upay) · Track 05: Merchant & Agent Intelligence — Agent Liquidity Forecasting

> All results are from synthetic data for hackathon prototyping, not production upay data.

## 1. Problem

MFS agents need physical cash (for cash-out) and e-float (for cash-in). Demand varies by hour,
weekday, salary period, market days and local events. Static, once-a-day cash provisioning cannot
anticipate these swings, so agents run dry at peak times, customers are turned away and rebalancing
is reactive. We present AgentFlow as a future-ready capability for any MFS network; we do not claim
evidence of a specific problem at upay.

## 2. User

Liquidity / distribution operations analysts and supervisors who oversee agent networks, and the
field staff who execute approved rebalancing.

## 3. Why the problem matters

* **Customers:** a failed cash-out is a direct service failure, often at moments of need (salary day).
* **Agents:** lost commission and reputational damage.
* **Operator:** lower service availability, more emergency logistics and support costs.
* In the synthetic status-quo simulation, 140 of 200 agents experience shortages in two weeks and
  BDT 95.4 lakh of cash-out demand goes unmet.

## 4. Proposed solution

A closed intelligence loop — **forecast → risk → explain → recommend → human review → simulate →
measure impact** — delivered as an operations dashboard backed by an API:
Command Center, Agents, Agent Intelligence, Rebalancing Center, Scenario Lab, Impact & Model Health,
Responsible AI.

## 5. AI role

| Need | AI / algorithm | Why it is needed |
|---|---|---|
| Where will cash be needed? | gradient-boosted forecasts of 6-h cash-out and peak cash requirement, P90 quantile | demand patterns interact (hour × weekday × salary × agent); ML beats naive and seasonal rules by 22–37% MAE |
| Is behaviour unusual? | Isolation Forest + robust deviation hybrid | unsupervised detection of surges, odd-hour activity, churn |
| How urgent? | deterministic risk engine | transparent, auditable prioritisation |
| What to do? | constrained optimiser: policy V2 (default: benefit gate, dynamic donor reserve, benefit–cost–safety ranking) and the original nearest-donor V1 | turns predictions into safe, concrete actions |

No LLM is used for decisions; the core system works without any external AI service.

## 6. Data strategy

Seeded synthetic generator: 200 agents, 8 districts, 76 days hourly (364,800 rows). Injected
patterns: daily cycles, Bangladesh weekend, salary period, rural market days, AR(1) regimes, local
spikes, noise; a status-quo daily drawer-reset policy; 426 labelled anomaly episodes. No PII.
Time-based purged split: train 2026-06-24 → 08-17, test 2026-08-18 → 08-31. See `DATA_CARD.md`.

## 7. Model architecture

* 31 leakage-safe features (calendar, agent attributes, lags, rolling stats, same-window history, velocity).
* Three `HistGradientBoostingRegressor` models: cash demand (Poisson), peak requirement (squared
  error), peak requirement P90 (quantile).
* Hybrid anomaly detector on agent-relative one-sided deviations.
* Risk = coverage (45) + P90 tail (20) + shortfall size (20) + velocity (10) + history (5).
* Rebalancing: same district, ≤ 15 km, LOW-risk donors keep ≥ 110% of their own P90 requirement (V1). The
  default V2 adds a dynamic donor reserve that grows with uncertainty, velocity and shortage history; a
  minimum-benefit gate; and donor ranking by benefit, safety and cost. Its parameters were selected on
  training-period validation folds.
See `MODEL_CARD.md`.

## 8. Product architecture

Python ML package (`ml/agentflow`) → FastAPI service (`apps/api`) → Next.js dashboard (`apps/web`).
One decision engine powers dashboard snapshots, API and impact simulator. See `ARCHITECTURE.md`.

## 9. Prototype features

* Decision-time replay of any held-out hour.
* Command Center KPIs, 48-h forecast-vs-actual trend, risk distribution, top at-risk agents,
  urgent recommendations, district view.
* Filterable / sortable agent table.
* Agent Intelligence: forecasts with P90, risk components, *Why this risk?*, anomaly drivers,
  recommended action, 72-h history, model evidence.
* Rebalancing Center: evidence drawer, protected-level visualisation, acknowledgement,
  **Approve Simulation**, portfolio before/after, audit log, escalations, held-for-review.
* Scenario Lab: network / district demand shocks recomputed live.
* Impact & Model Health: policy comparison, baselines vs. ML, alert and anomaly evaluation, fairness.

## 10. Evaluation (synthetic held-out)

| Area | Result |
|---|---|
| Cash-demand forecast | MAE 6,138 vs. 7,890 seasonal / 9,691 naive (−22.2% / −36.7%) |
| Peak-requirement forecast | MAE 5,147 vs. 5,524 seasonal (−6.8%); RMSE −12.7% |
| Uncertainty | P90 coverage 89.5% (nominal 90%) |
| Early warning (HIGH+) | precision 81.5%, recall 41.7%, AUC 0.935 (naive-fed: 84.5%, 31.3%, 0.911) |
| Risk calibration | observed shortage rate LOW 3.7% · MEDIUM 59.5% · HIGH 79.3% · CRITICAL 86.1% |
| Anomaly detection | ROC-AUC 0.981, AP 0.671 (a simple rule alone is equally strong — reported) |

See `EVALUATION.md`.

## 11. Business / customer impact (synthetic held-out simulation)

Same demand, same total cash, 14 days, 200 agents:

| | Without AgentFlow | AgentFlow V1 | **AgentFlow V2 (default)** |
|---|---:|---:|---:|
| Shortage events | 2,017 | 1,255 (−37.8%) | **1,223 (−39.4%)** |
| Unmet cash demand | BDT 95.4 lakh | BDT 58.3 lakh (−38.9%) | **BDT 56.9 lakh (−40.3%)** |
| Service availability | 96.76% | 97.92% | **97.95%** |
| Transfers | — | 501 | **345** |
| Donor shortage events within 6 h | — | 25 | **14** |
| Estimated logistics cost | — | BDT 1.58 lakh | **BDT 1.15 lakh** |
| Unnecessary transfers | — | **21.4%** | 24.3% |
| Extra cash injected | — | BDT 0 | BDT 0 (peer rebalancing only) |

V2 delivers slightly more benefit than V1 with 31% fewer transfers, 27% lower logistics cost and 44%
fewer donor shortage events. The share of unnecessary transfers did not improve (24.3% vs 21.4%), and V2
is slightly worse than V1 for rural agents. It became the default under a deployment rule written before
the held-out evaluation. Rebalancing fed by a naive forecast achieves −26.5% events, isolating the ML
contribution.

## 12. Responsible AI

Synthetic data and tested absence of PII; deterministic, evidence-based explanations; source tags
(ML prediction / calculation / recommendation / simulation / synthetic data); human review with
explicit acknowledgement; simulation-only approvals with audit log; hard donor-safety constraints;
anomaly ≠ fraud and anomalous agents routed to manual review; operational-group consistency checks;
input validation, structured errors and env-based configuration.

## 13. Limitations

Synthetic, hand-designed data; modest gain on the peak-requirement target; ~42% recall of shortage
windows; false-alert and donor-risk costs; simplified logistics (1-hour transfers, cost model);
exogenous demand; e-float not binding; in-memory audit log; no authentication.

## 14. Scalability

Vectorised feature pipeline and gradient boosting train in seconds on 260k rows and predict all
agents in one batch; the API serves cached snapshots in tens of milliseconds. Path to scale: warehouse
feature jobs, nightly retraining behind the same time-based evaluation gate, database-backed audit and
approvals with RBAC, webhook hand-off of *approved* actions to existing field workflows, and a
min-cost-flow optimiser if routing constraints are added.

## 15. Future real-data validation

1. Hourly per-agent aggregates (no customer data), including declined cash-out attempts.
2. Re-run the unchanged pipeline with the same baselines and split.
3. Back-test the impact simulator against historical rebalancing logs and distributor constraints.
4. Shadow-mode pilot with operations staff; record decisions and outcomes.
5. Monitor forecast error, P90 coverage, alert precision/recall and group consistency.

## 16. Conclusion

AgentFlow shows that agent liquidity stress can be anticipated hours ahead, explained with concrete
evidence, and converted into safe, human-approved peer rebalancing that — in a reproducible held-out
simulation — avoids about 38% of shortage events without adding cash to the network.
