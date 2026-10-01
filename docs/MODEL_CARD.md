# Model Card — AgentFlow AI

> Decision-support prototype trained and evaluated on **synthetic data for hackathon prototyping —
> not production upay data**. Not validated on real operations.

## 1. Purpose

Help an MFS operations team anticipate agent-level cash liquidity stress over the next 6 hours,
understand why it is predicted, and review safe peer rebalancing recommendations — before
customers are turned away.

AgentFlow is **not** an autonomous system. It never moves money, never sends instructions, and
never labels anyone fraudulent.

## 2. Intended users

* Liquidity / distribution operations analysts and supervisors.
* Area managers or field officers who execute (real-world) rebalancing after human approval.

Not intended for: credit decisions, agent performance evaluation, fraud adjudication, or any
decision about individual customers.

## 3. Components

| Component | Type | Output |
|---|---|---|
| Cash-demand forecaster | `HistGradientBoostingRegressor`, Poisson loss | next-6h requested cash-out per agent |
| Peak-requirement forecaster | `HistGradientBoostingRegressor`, squared error | next-6h peak cumulative net cash drain (P50) |
| Uncertainty model | `HistGradientBoostingRegressor`, quantile loss α = 0.9 | P90 of the peak requirement |
| Behavioural anomaly detector | Isolation Forest + robust deviation rule (percentile average) | score ∈ [0, 1], NORMAL / WATCH / ANOMALOUS |
| Liquidity risk engine | deterministic formula | 0–100 score, LOW / MEDIUM / HIGH / CRITICAL, reasons |
| Rebalancing policy V1 | greedy nearest-donor optimiser | peer transfers, escalations, holds |
| Rebalancing policy V2 (default) | constrained optimiser with dynamic donor reserve, minimum-benefit gate, benefit–cost–safety ranking | peer transfers with benefit and safety evidence, escalations, holds |

## 4. Features (forecasting, 31 total — all observable at decision time)

* Calendar: hour, day of week, weekend, salary period, day of month, market day today / tomorrow.
* Agent attributes (encoded): district, location cluster, volume segment, agent type.
* Cash-out history: last hour, 3/6/24-h sums, 24-h mean and std, 168-h mean, same 6-h window
  yesterday / last week / 7-day average.
* Cash-in history: 6/24-h sums, 168-h mean, same window yesterday / 7-day average.
* Realised peak requirement of the same window on previous days (1 d, 7 d, 7-day avg).
* Activity: 3-h transaction count, velocity ratio vs. the same hours on the previous 7 days.

Cash balance is deliberately **not** a forecasting feature: customer demand is treated as exogenous;
balances enter only in the risk engine.

Anomaly features (agent-relative, one-sided surges): cash-out, cash-in and cash-out-count deviation
vs. the same hour on the previous 7 days; cash-out ticket-size deviation vs. the 7-day average;
simultaneous in/out surge (churn); night-time activity; 3-h velocity deviation.

## 5. Training and testing

* Data: 200 synthetic agents, hourly, 2026-06-17 → 2026-08-31 (see `docs/DATA_CARD.md`).
* Split: time-based; train 2026-06-24 → 2026-08-17 17:00 (262,800 rows, 6-h purge),
  test 2026-08-18 → 2026-08-31 (66,000 rows). No shuffling. Anomaly thresholds and per-agent
  historical shortage rates use the training period only.
* Reproducible: fixed seeds; `python ml/scripts/run_pipeline.py`.

## 6. Metrics (held-out, synthetic)

| | ML | Best baseline | Improvement |
|---|---:|---:|---:|
| Cash-demand MAE | BDT 6,138 | BDT 7,890 (seasonal) | −22.2% |
| Cash-demand RMSE | BDT 11,816 | BDT 15,636 | −24.4% |
| Peak-requirement MAE | BDT 5,147 | BDT 5,524 (seasonal) | −6.8% |
| Peak-requirement RMSE | BDT 10,138 | BDT 11,612 | −12.7% |
| P90 empirical coverage | 89.5% | nominal 90% | — |
| Risk alerts (HIGH+) precision / recall / AUC | 81.5% / 41.7% / 0.935 | 84.5% / 31.3% / 0.911 (naive-fed) | +10.4 pp recall |
| Anomaly ROC-AUC / AP | 0.981 / 0.671 | rule-only 0.982 / 0.671 | on par |

Full details, impact simulation and group analysis: `docs/EVALUATION.md`.

## 7. Risk logic

`risk_score = coverage (≤45) + tail_risk (≤20) + deficit_size (≤20) + velocity (≤10) + history (≤5)`

* coverage = 45 · clip((1.25 − cash / P50 requirement) / 1.25, 0, 1)
* tail_risk = 20 · clip(1 − cash / P90 requirement, 0, 1)
* deficit_size = 20 · clip(expected shortfall / BDT 40,000, 0, 1)
* velocity = 10 · clip(velocity_ratio_3h − 1, 0, 1)
* history = 5 · clip(training-period shortage rate / 0.15, 0, 1)

Levels: LOW < 25 ≤ MEDIUM < 50 ≤ HIGH < 75 ≤ CRITICAL. Requirements below BDT 1,000 count as
"no material requirement". The score is monotone: less cash or a larger forecast can never lower it
(unit-tested). Weights were set a priori from operational reasoning, not fitted to the test set.

## 8. Anomaly logic

Score = mean of the training-percentile of the Isolation Forest score and the training-percentile
of the maximum robust z-score across features. WATCH ≥ 99.0th, ANOMALOUS ≥ 99.7th training
percentile. Agent status uses the worst hour in the last 6 hours. Anomalies **do not** change the
liquidity risk score; they raise review priority, and at-risk agents with ANOMALOUS status are held
for manual review rather than receiving rebalancing recommendations.

## 8a. Rebalancing policy V2

* **Dynamic donor reserve**, never weaker than V1:
  `max(5,000, 1.10·P90, (P90 + u·(P90−P50)) × (1 + 0.5·clip(velocity−1,0,1)) × (1 + 0.5·clip(history/0.15,0,1)))`.
  Donors must still be LOW risk after the complete plan.
* **Recipient target:** `P50 + λ·(P90 − P50)`.
* **Minimum-benefit gate:** a leg must lower the recipient's risk level, cut its score by ≥ `min_risk_drop`
  points, or remove ≥ 50% of its P50 expected shortfall; otherwise the need is escalated.
* **Donor ranking (lexicographic):** covers the remaining need alone → recipient risk points removed per
  BDT 100 of cost → donor margin above reserve → distance.
* **Parameters:** λ = 1.0, u = 0.25, `min_risk_drop` = 20. They were selected on two chronological
  validation folds inside the training period, with out-of-sample fold models. The held-out test
  period was used once.
* **Held-out result** (synthetic) vs V1: unmet demand −40.3% vs −38.9%; 345 vs 501 transfers; 14 vs 25
  donor shortage events; BDT 1.15 vs 1.58 lakh logistics cost. The unnecessary-transfer share was
  24.3% vs 21.4% (worse). V2 is the default under a pre-registered rule; V1 remains selectable.
  See `docs/EVALUATION.md` §5a.

## 9. Explainability

* **Local:** every "Why this risk?" statement is generated from computed evidence — forecast P50/P90,
  coverage, expected shortfall, P90 gap, velocity ratio, historical shortage rate, same-window
  seasonal uplift, salary period, market day — each with its point contribution.
* **Anomaly drivers:** the most deviating features with "× usual" ratios.
* **Global:** permutation importance of the forecaster on held-out data.
* **Source tagging:** the UI labels each number as ML prediction, deterministic calculation,
  recommendation, simulation, or synthetic data.
* No LLM is used anywhere in the decision path.

## 10. Responsible-AI considerations

* Privacy: synthetic data only; no PII fields (tested).
* Human oversight: approval requires opening the evidence and an explicit acknowledgement; approval
  only simulates and is written to an audit log.
* Safety constraints: donor safe-surplus cap, protected level (110% of own P90), same district,
  ≤ 15 km, no negative balances (tested).
* Fairness: consistency across location clusters and volume segments reported; lower recall for
  rare-shortage urban-core agents and smaller gains for sparse rural networks are disclosed.
* Security: input validation, structured errors without stack traces, env-based configuration,
  configurable CORS.

## 11. Known limitations

* Synthetic, hand-designed data; no real-world validation.
* Peak-requirement forecast gain over the seasonal baseline is modest.
* HIGH+ alerts catch ~42% of shortage windows; many shortages arise from short spikes that are hard
  to anticipate 6 hours ahead.
* Donor protection relies on the donor's own forecast. Donor shortage events still occur: 14 across
  345 simulated transfers with V2 (V1: 25 across 501).
* V2 did not reduce the share of unnecessary transfers (24.3% vs 21.4%) and is slightly worse than V1
  for rural agents.
* No modelling of e-float limits, distributor capacity, travel time or cash-in-transit security.

## 12. When not to trust the system blindly

* Unseen regimes: Eid / festivals, disasters, network outages, regulatory or pricing changes.
* Agents with < 7 days of history (features incomplete) or recently re-located agents.
* Agents showing unusual behavioural activity — review the activity first.
* When forecast error monitoring (MAE vs. baseline, P90 coverage) drifts from the evaluated values.
* Before validation on real, consented operational data and a supervised pilot.
