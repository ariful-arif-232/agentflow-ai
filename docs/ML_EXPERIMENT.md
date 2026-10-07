# Targeted ML experiment (Phase 2)

> **Synthetic controlled experiment.** Selection used training-period validation folds only; the held-out
> period was evaluated once, after the success criteria were fixed. Not real upay performance.

Judges raised two AI/ML weaknesses:

1. The peak cash-requirement forecast beats the seasonal baseline by only **6.8% MAE**.
2. HIGH+ early-warning alerts catch only **41.7%** of shortage windows.

This experiment tested targeted fixes under a pre-registered protocol. **Outcome:**

* **No forecasting candidate earned promotion**, so the serving forecast models and every published
  Phase-1/Phase-2 metric are unchanged.
* **A lower alert operating point (MEDIUM+) was adopted as the early-warning definition.** It raises recall
  to 63.0% at 72.4% precision. Risk levels and rebalancing are unchanged.

| Piece | File |
|---|---|
| Candidate features, models, criteria | `ml/agentflow/ml_experiment.py` |
| Experiment script (select → held-out) | `ml/scripts/ml_experiment.py` |
| Pre-registration record (validation only) | `ml/artifacts/ml_experiment_preregistration.json` |
| Versioned result | `ml/artifacts/ml_experiment.json` (`phase2-ml-1`) |
| API / UI | `GET /api/ml-experiment`; Impact & Model Health → **Targeted ML experiment** |
| Tests | `tests/test_ml_experiment.py` (11 tests) |

## 1. Protocol

1. **Validation folds inside the training period:**
   * fold A: 2026-07-21 → 08-03;
   * fold B: 2026-08-04 → 08-17.

   Each candidate is re-trained on rows whose 6-hour target window ends before the fold starts. It is
   scored only on rows whose target window ends inside the fold. Fold B's last scored row is 2026-08-17
   17:00, and its target ends at 23:00, before the held-out period starts. `assert_selection_rows_before_test`
   enforces this, and a test checks it.
2. **Pre-registered criteria** (`CRITERIA` in code) were written before any held-out evaluation. They are
   stored with their SHA-256 in the pre-registration file. The held-out stage refuses to run if the
   criteria changed.
3. **Held-out evaluation, run once:** the current serving model and the validation-selected candidate on
   2026-08-18 → 08-31.

## 2. Candidates

| Candidate | What changes |
|---|---|
| `spatial` | Adds same-district aggregates (excluding the agent itself) and aggregates over the 5 nearest outlets: cash-out regime ratio, transaction-velocity ratio and 24-hour shortage share. Strictly lagged: neighbours' data up to hour *t−1* only. |
| `temporal` | Adds today's cash-out and cash-in so far against the same hours on the previous 7 days, yesterday's total against its 7-day average, the 24-hour regime ratio, and the spread of the same-window history. |
| `spatial_temporal` | Both feature families. |
| `temporal_ensemble` | Temporal features; an average of 3 feature-bagged gradient-boosting models (different seeds) from the existing stack; optionally blended with the seasonal baseline (weight chosen on validation from 0, 0.1, 0.2, 0.3). |
| Alert operating point | Risk-score thresholds 50 (current HIGH), 45, 40, 35, 30 and 25 (= MEDIUM+), computed with fold-trained current models. |

Leakage tests check three things:

* Scrambling all data after a time *T0*, including labels, leaves every candidate feature at hours ≤ *T0*
  unchanged.
* Neighbours do not see an agent's hour-*T0* data until *T0*+1.
* An agent's own data never enters its district aggregate.

The candidate code never reads anomaly labels or future targets, except for the existing day-lagged
same-window history.

## 3. Pre-registered criteria

**Selection (validation only).**

* Forecast: the candidate with the lowest pooled peak-requirement MAE goes to the held-out stage only if
  * it is at least 1% below the current configuration's MAE,
  * validation P90 coverage is within [0.87, 0.93], and
  * cash-demand MAE is no more than 1% worse.
* Alert: the lowest threshold with pooled validation precision ≥ 0.70.

**Promotion of a forecast model (held-out).** All of the following must hold:

* peak MAE ≤ 0.97 × current, and ≥ 10% better than the seasonal baseline;
* cash-demand MAE ≤ 1.01 × current;
* P90 coverage within [0.87, 0.93];
* HIGH+ recall falls by no more than 1 pp, and precision by no more than 5 pp;
* downstream V2 unmet cash-out and shortage events are each no more than 2% worse, and donor shortages are
  at most +2;
* the leakage tests pass.

**Adoption of an alert operating point (held-out).** All of the following must hold:

* recall improves by ≥ 10 pp over HIGH+;
* precision is ≥ 0.70;
* alert volume is ≤ 3× HIGH+.

The scope is the early-warning definition only: risk levels and rebalancing recipients are unchanged.

## 4. Validation results (selection stage)

| Candidate | Peak MAE (pooled) | vs current | P90 coverage | Passes gate |
|---|---:|---:|---:|---|
| current | 5,171.2 | — | 88.9% | — |
| spatial | 5,186.5 | **+0.30% (worse)** | 88.6% | no |
| temporal | 5,123.9 | −0.91% | 88.8% | no |
| spatial_temporal | 5,154.2 | −0.33% | 88.5% | no |
| temporal_ensemble (blend 0.1) | 5,084.4 | **−1.68%** | 88.9% | **yes → selected** |

Spatial features did not help. The synthetic generator draws each agent's demand regime and spikes
independently, so there is no cross-agent signal to learn. This is reported as a negative result.

Alert thresholds on validation (precision / recall):

| Threshold | Precision | Recall |
|---:|---:|---:|
| 50 | 0.801 | 0.413 |
| 45 | 0.794 | 0.457 |
| 40 | 0.781 | 0.502 |
| 35 | 0.767 | 0.546 |
| 30 | 0.747 | 0.593 |
| 25 | 0.721 | 0.640 |

Threshold 25 was selected as the lowest with precision ≥ 0.70.

## 5. Held-out results (evaluated once)

| Metric | Current (serving) | Candidate `temporal_ensemble` | Rule | Pass |
|---|---:|---:|---|---|
| Peak-requirement MAE | 5,147.1 | 5,044.8 (**−1.99%**) | ≤ −3% | **no** |
| Improvement vs seasonal (5,523.6) | 6.82% | **8.67%** | ≥ 10% | **no** |
| Cash-demand MAE | 6,137.8 | 5,980.4 (−2.6%) | ≤ +1% | yes |
| P90 coverage | 89.49% | 89.44% | 87–93% | yes |
| HIGH+ recall / precision | 41.65% / 81.48% | 41.09% / 80.91% | ≥ −1 pp / ≥ −5 pp | yes |
| V2 shortage events | 1,223 | **1,266 (+3.5%)** | ≤ +2% | **no** |
| V2 unmet cash-out (BDT) | 5,690,940 | 5,690,340 | ≤ +2% | yes |
| V2 donor shortage events | 14 | 15 | ≤ +2 | yes |

**Forecast decision: rejected.** It failed 3 of 10 criteria. The serving model is unchanged. The candidate
gives a real but small gain (about 2%), which is below the pre-registered materiality bar, and it
slightly worsened downstream V2 shortage events.

**Alert operating point** (current serving model, held-out):

| Alert when risk score ≥ | Recall | Precision | Alerts | False alert-hours / 100 agents / day |
|---:|---:|---:|---:|---:|
| 50 (HIGH+, rebalancing tier) | 41.65% | 81.48% | 1,798 | 11.9 |
| 45 | 46.20% | 80.73% | 2,013 | 13.9 |
| 40 | 49.79% | 79.23% | 2,210 | 16.4 |
| 35 | 53.43% | 77.74% | 2,417 | 19.2 |
| 30 | 57.69% | 75.37% | 2,692 | 23.7 |
| **25 (MEDIUM+, adopted early warning)** | **63.01%** | **72.42%** | 3,060 | 30.1 |

**Alert decision: adopted.**

* Recall +21.4 pp; precision −9.1 pp (still ≥ 0.70); alert volume 1.70× HIGH+.
* The gain comes from the **operating point, not a better model**: the same scores, read at a lower
  threshold. About one MEDIUM+ alert in four is a false alarm.
* AgentFlow now reports two tiers:
  * **early warning = MEDIUM+** (watch);
  * **action = HIGH+** (rebalancing recipients, unchanged).

## 6. What did not change

The following are unchanged:

* forecast models;
* anomaly detector and thresholds;
* risk formula and levels;
* rebalancing V1/V2 and their parameters;
* Morning Plan, logistics, security, business impact and integration evidence;
* `metrics.json`, `impact.json` and the other published artifacts.

The current arm of the experiment reproduces `metrics.json` and `impact.json` exactly, and a test checks
this.

## 7. Limitations

* There is one synthetic world. The 2% candidate gain might be larger or smaller on real data, and real
  data might contain the cross-agent correlation that the generator lacks. Spatial features should be
  re-tested on real data.
* Hourly demand noise in the generator (lognormal, σ ≈ 0.33 per hour) is independent. It is likely to
  dominate the remaining peak-requirement error. We did not quantify this ceiling.
* The alert operating point was chosen for a 0.70 precision floor. Operations teams may prefer another
  point, and the full curve is published.
* The pre-registration and the held-out run are in the same commit. The protocol is enforced in code: the
  hash check, and selection data that never reaches the held-out period.

Reproduce: `python ml/scripts/ml_experiment.py` (about 6 minutes; `--stage select` runs validation only).
