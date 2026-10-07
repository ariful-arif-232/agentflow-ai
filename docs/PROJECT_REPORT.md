# AgentFlow AI — Project Report (outline-ready)

**Explainable Predictive Liquidity Orchestration for MFS Agent Networks** · *Same liquidity. Placed ahead of demand.*
AI DEV FEST 2026 AI Hackathon (DIU CPC × upay) · Track 05: Merchant & Agent Intelligence — Agent Liquidity Forecasting

> All results are from synthetic data for hackathon prototyping, not production upay data.

## 1. Problem

> For MFS liquidity operations teams, agents running short of physical cash or e-float during demand
> peaks can cause failed customer transactions and lost agent income. AgentFlow uses per-agent
> transaction-flow aggregates to forecast liquidity need and recommend human-reviewed placement
> decisions, with success measured by unmet demand under the same working-capital budget.

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
* **Economics (illustrative formula only):** protected agent income ≈ avoided unmet transaction
  value × verified applicable commission rate. We do not assume a commission rate. Operator-specific
  economics must come from validated real data.

## 4. Proposed solution

*Same liquidity. Placed ahead of demand.* AgentFlow works on two time scales:
* **Morning:** predict each agent's full-day cash and e-float need and recommend where the same
  district working capital should sit (Morning Liquidity Plan).
* **Intraday:** monitor cash pressure and recommend safe V2 peer recovery, through the loop
  **forecast → risk → explain → recommend → human review → simulate → measure impact**
  (*Predict. Explain. Rebalance.*).
* **Human:** a person reviews every consequential action; approval only simulates.
* **Measure:** each layer is evaluated in its own synthetic environment.

It is delivered as an operations dashboard backed by an API: Command Center, Morning Plan, Agents,
Agent Intelligence, Rebalancing Center, Scenario Lab, Impact & Model Health, Responsible AI.

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
* **Morning Liquidity Plan** (proactive):
  * full-day cash + e-float positioning with the same working capital, and exact per-district
    conservation;
  * review focus, an agent explanation drawer and human-review simulation;
  * historical research evidence with caveats.

## 10. Evaluation: intraday system (synthetic held-out, legacy environment)

In this legacy environment, e-float is tracked but is not a binding constraint. The Morning Plan is
evaluated separately (§10a).

| Area | Result |
|---|---|
| Cash-demand forecast | MAE 6,138 vs. 7,890 seasonal / 9,691 naive (−22.2% / −36.7%) |
| Peak-requirement forecast | MAE 5,147 vs. 5,524 seasonal (−6.8%); RMSE −12.7% |
| Uncertainty | P90 coverage 89.5% (nominal 90%) |
| Early warning (HIGH+) | precision 81.5%, recall 41.7%, AUC 0.935 (naive-fed: 84.5%, 31.3%, 0.911) |
| Risk calibration | observed shortage rate LOW 3.7% · MEDIUM 59.5% · HIGH 79.3% · CRITICAL 86.1% |
| Anomaly detection | ROC-AUC 0.981, AP 0.671 (a simple rule alone is equally strong — reported) |

See `EVALUATION.md`.

## 10a. Morning Liquidity Plan: two time scales

AgentFlow now works on two time scales:
* **Proactive:** a full-day dual-liquidity Morning Plan for cash and e-float, at 07:00 → 08:00.
* **Reactive:** the 6-hour cash risk with V2 rebalancing.

The Morning Plan is evaluated in a **separate** synthetic environment, Dual-Liquidity World v2, where
physical cash **and** e-float are both binding. It is not combined with the legacy intraday
simulation in §10–§11.

In fresh synthetic worlds from the same world family, the frozen full-day ML policy reduced combined
unmet demand by a median **20.6%** versus the strongest cautious historical baseline, while
conserving each district's cash and e-float budgets exactly. **This is synthetic held-out evidence,
not measured upay performance, and not an expected saving for any demo date.**

* **Success bar.** The protocol and success bar were committed before the audit seeds (2036–2040)
  were generated. ML had to:
  * match or beat both the 7-day q90 and 7-day max rules in at least 4 of 5 worlds;
  * reach a median combined-unmet reduction of at least 5% against the better of the two;
  * worsen cash or e-float unmet by more than 5% in at most 1 world;
  * conserve both budgets exactly.

  All five checks passed.
* **Absolute example (audit world seed 2036, 14 held-out operating days).** Combined unmet fell
  from about BDT 49.7 lakh (q90 rule) to about BDT 40.8 lakh (frozen ML), −17.9% in this world.
  Cash-out fill rose from 99.65% to 99.80%.
* **Who moves the liquidity?** AgentFlow only recommends target levels and simulates approval; it
  never executes a transfer. A future deployment could hand approved targets to an existing
  distributor, field-officer or bank-deposit replenishment workflow. Whether targets can change daily
  is a real-world validation question.

For every research step, the protocol and success bar were committed before results were computed,
and the negative results are kept:
1. peer cash/e-float swaps were rejected (local complementarity was sparse);
2. a 6-hour ML morning plan was rejected (seasonal full-day history beat it);
3. the forecast horizon was aligned to the full-day decision (confirmatory seeds 2031–2035);
4. the frozen model survived cautious-baseline (q90/max) attribution (audit seeds 2036–2040).

Caveats: cash P90 coverage is about 85% (nominal 90%), low-volume agents did worse than q90 in 4 of 5
worlds, and rural e-float can fall materially. See `MORNING_PLAN.md`.

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
is slightly worse than V1 for rural agents. It became the default under a fixed deployment rule, with parameters
selected on training-period validation folds only. Rebalancing fed by a naive forecast achieves −26.5% events, isolating the ML
contribution.

## 11a. Phase-2 logistics economics (synthetic operational-cost proxy)

Phase-1 judges asked for distributor transport and cash-in-transit costs in the rebalancing loss
function. Without governed upay rates, Phase 2 adds a transparent, configurable **synthetic
operational-cost proxy** (`ml/agentflow/logistics.py`), shared by V1, V2 and the simulator:

`total = handling + round-trip km × per-km cost + (round-trip km ÷ field speed + handling time) ×
hourly field-officer cost + amount × cash-in-transit bps`

The demo defaults (BDT 100 handling, ×2 round trip, BDT 12/km, 15 km/h, 15 min handling, BDT 250/h,
10 bps) are illustrative, not upay or distributor rates. They can be overridden with
`AGENTFLOW_LOGISTICS_<FIELD>` environment variables, so governed operator rates can replace them without
code changes. Escalations get a distributor-trip proxy from a synthetic district hub (district centroid;
no real distributor location is implied).

* **The serving V2 keeps the proven Phase-1 ranking**; the proxy costs its transfers. As an experiment,
  ranking donors by the proxy changed 13 of 345 held-out transfers and was slightly worse (shortage events
  1,223 → 1,229, unmet demand −40.3% → −40.2% vs status quo, donor shortage events 14 → 15), so it was not
  adopted. It is kept as labelled experimental evidence and runs only when requested explicitly.
* Derived held-out metrics for the serving V2: peer-transfer cost proxy BDT 2.09 lakh (BDT 607 per
  transfer, cash-in-transit BDT 7,512), distributor escalation proxy BDT 4.69 lakh (upper bound), total
  BDT 6.78 lakh, BDT 18,360 of unmet demand avoided per BDT 1,000 of peer-transfer cost.
* The Phase-1 table above is unchanged and remains reproducible. Details: `EVALUATION.md` §9.

*Simulated operational-cost proxy — replace assumptions with governed operator rates for deployment.*

## 11b. Phase-2 business impact (synthetic simulated estimate)

*Synthetic simulated estimate — not measured upay performance.* A separate, versioned layer
(`business_impact.json`, `GET /api/business-impact`) translates the same held-out simulation into
business terms without changing any earlier number. Over 14 held-out days, the serving V2 (Phase-1
ranking) against the status quo:

* **Customers:** BDT 38.5 lakh of requested cash-out served that was unmet (direct); ≈ 2,466 cash-out
  transactions protected (**estimate**: unmet BDT ÷ average synthetic ticket; range 2,438–2,466); 794 fewer
  shortage agent-hours.
* **Agents:** illustrative commission protected BDT 19,230 at an **assumed 50 bps** (not upay's or any
  provider's rate; configurable).
* **Distributor and logistics:** 345 peer transfers (cost proxy BDT 2.09 lakh, BDT 607 each); 154
  escalated agent-days (distributor trip proxy BDT 2.35 lakh, break-even fee BDT 1,524 per trip).
* **Economics:** commission does not cover the peer logistics proxy (net −BDT 1.90 lakh; break-even
  ≈ 545 bps), and a 25–200 bps × 0.5–1.5× cost sensitivity grid stays negative. The value lies in customers
  served and in cheaper delivery: BDT 85 of logistics per protected transaction for V2 against BDT 116 for
  V1. No ROI is claimed. Details: `EVALUATION.md` §10.

## 11c. Phase-2 security, approval and manipulation guardrails (prototype controls)

* **Server-enforced approval:** `POST /api/rebalancing/simulate` now requires `reviewer_acknowledged: true`
  (strict boolean); the Morning Plan endpoint already did. A direct API call cannot bypass it.
* **Replay guard:** a deterministic fingerprint of what is approved (decision time, policy, recommendations;
  or the Morning Plan date) means a repeated approval returns the original audit record.
* **Rate limiting:** process-local sliding window on the two simulation endpoints only (default 20 per 60 s
  per client; HTTP 429 with `Retry-After`). Not an enterprise WAF.
* **Tamper-evident audit:** each simulated approval is SHA-256 hash-chained (`previous_hash`,
  `record_hash`) and verified; edits break the chain and new approvals are refused (fail closed). Optional
  append-only JSONL file (`AGENTFLOW_AUDIT_LOG_PATH`), re-verified at start-up. Not production-grade
  immutable storage; durability needs a persistent volume or an external governed audit store.
* **Manipulation guardrail evidence:** with the unchanged Phase-1 detector and thresholds, a manufactured
  4-hour transaction surge on an at-risk agent raises it to ANOMALOUS, and both policies then hold it for
  manual review with no peer-liquidity recommendation. Milder manipulation can stay below the thresholds,
  and WATCH-level at-risk agents are not held; both are documented limitations.
* **Authentication:** not implemented (no secret is placed in the browser). Enterprise identity and
  role-based approval remain production requirements.

## 11d. Phase-2 integration & scale (synthetic benchmark evidence)

*Synthetic benchmark evidence — not real upay production performance, and not a real upay integration.*

* **Feed contract `agentflow.feed.v1`:** aggregated agent-hours plus an agent registry, with no personal
  data. Validation is strict (unknown and personal-data-like fields rejected, hour-aligned timestamps,
  finite non-negative amounts, integer counts, served ≤ requested, whole-batch rejection), and the
  contract maps one-to-one onto the existing pipeline inputs.
* **Replay equivalence:** a chronological replay of the stored dataset through the contract (362,800
  events) reproduces the batch pipeline's decision snapshot exactly at four held-out timestamps, for all
  200 agents. The replay is deterministic.
* **Benchmark** (median hourly refresh, 4 vCPUs): 0.61 s for 200 agents, 2.3 s for 1,000, 12.0 s for
  5,000 and 23.6 s for 10,000, with peak memory 1.9 GB at 10,000.
* **Bottleneck:** the whole 216-hour window is recomputed on every refresh (about 80% of the time at
  10,000 agents). Incremental caching is not implemented.

Details: `docs/INTEGRATION.md`.

## 11e. Phase-2 targeted ML experiment (pre-registered)

* **Question:** can the peak-requirement forecast (only −6.8% MAE vs seasonal) or HIGH+ recall (41.7%)
  improve without tuning on the test period?
* **Protocol:** candidates were selected on two purged training-period validation folds. The success
  criteria were fixed and hashed first, and the held-out period was evaluated once.
* **Forecast candidates:** lagged spatial/neighbour aggregates (worse on validation), temporal regime
  features, and a temporal 3-seed ensemble. The best one reduced held-out peak MAE by only 1.99% (8.7% vs
  seasonal; the bar was 10%) and raised V2 shortage events by 3.5%. **Rejected; the serving model is
  unchanged.**
* **Alert operating point:** MEDIUM+ (risk score ≥ 25) was adopted as the early-warning tier. Recall is
  63.0% vs 41.7% and precision 72.4% vs 81.5%. HIGH+ remains the action tier, and risk levels and
  rebalancing are unchanged.

Details: `docs/ML_EXPERIMENT.md`.

## 12. Responsible AI

Synthetic data and tested absence of PII; deterministic, evidence-based explanations; source tags
(ML prediction / calculation / recommendation / simulation / synthetic data); human review with
explicit acknowledgement; simulation-only approvals with audit log; hard donor-safety constraints;
anomaly ≠ fraud and anomalous agents routed to manual review; operational-group consistency checks;
input validation, structured errors and env-based configuration.

## 13. Limitations

Synthetic, hand-designed data; modest gain on the peak-requirement target; ~42% recall of shortage
windows; false-alert and donor-risk costs; simplified logistics (1-hour transfers, cost model);
exogenous demand; e-float tracked but not binding in the legacy intraday environment (only the
separate Morning Plan world treats it as binding); in-memory audit log; no authentication.

## 14. Scalability

Vectorised feature pipeline and gradient boosting train in seconds on 260k rows and predict all
agents in one batch; the API serves cached snapshots in tens of milliseconds. A measured synthetic benchmark (§11d) runs a full
hourly refresh in 2.3 s for 1,000 agents and 23.6 s for 10,000 agents on 4 vCPUs. That is synthetic
benchmark evidence, not upay production performance. The main cost is recomputing the whole rolling window. Path to scale: warehouse
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
evidence, and converted into safe, human-approved peer rebalancing. In a reproducible synthetic
held-out simulation, the default V2 avoids about 39% of shortage events (V1: about 38%) without
adding cash to the network. In a separate synthetic environment, a frozen full-day Morning Plan
reduced combined cash and e-float unmet demand by a median 20.6% against the strongest cautious
historical rule, using the same working capital.
