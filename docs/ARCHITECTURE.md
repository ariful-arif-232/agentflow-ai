# Architecture — AgentFlow AI

```
 Synthetic data generator (seeded)            ml/agentflow/data_gen.py
                │  hourly agent ledger aggregates, labelled anomalies
                ▼
 Feature engineering (leakage-safe)           ml/agentflow/features.py
                │
       ┌────────┴─────────┐
       ▼                  ▼
 Forecast models      Anomaly detector         ml/agentflow/forecast.py · anomaly.py
 (P50, P90, demand)   (IForest + rule)
       └────────┬─────────┘
                ▼
 Liquidity risk engine (0–100, deterministic)  ml/agentflow/risk.py
                ▼
 Explainability (evidence-based reasons)       ml/agentflow/risk.py · anomaly.py
                ▼
 Rebalancing engine: V1 nearest-donor greedy  ml/agentflow/rebalance.py
   and V2 benefit/cost/safety-aware (default)  ml/agentflow/rebalance_v2.py · policy_selection.py
                ▼
 Decision engine snapshots (per decision time) ml/agentflow/engine.py
                ▼
 FastAPI service                               apps/api/app/
                ▼
 Operations dashboard (Next.js)                apps/web/
                ▼
 Human review → Approve Simulation → audit log
                ▼
 Held-out impact simulation                    ml/agentflow/impact.py
                ▼
 Evaluation artifacts / feedback               ml/artifacts/*.json · docs/EVALUATION.md
```

## Why each layer exists

| Layer | Why |
|---|---|
| **Synthetic data generator** | No production data is available or needed for a prototype. A seeded generator with documented patterns (daily cycles, weekends, salary periods, market days, regimes, spikes) and a realistic status-quo cash policy makes the problem learnable, the evaluation reproducible and the repository safe to publish. Its schema mirrors what a real ledger extract would provide, so it can be swapped out. |
| **Feature engineering** | One module computes every lag, rolling statistic and target so features can never drift between training, evaluation and serving. Leakage is prevented by construction and verified by a perturbation test. |
| **Forecast models** | Liquidity stress is a *future* event; the operations team needs to know where cash will be needed in the next 6 hours, not where it was needed. Gradient boosting is fast, accurate on tabular data and explainable via permutation importance. A P90 quantile model quantifies uncertainty and drives safety buffers. |
| **Anomaly detector** | Unusual behaviour (bursts, odd-hour activity, churn) should change *how* a case is handled — manual review before liquidity support — without being conflated with liquidity risk or with fraud. |
| **Risk engine** | A deterministic, monotone, bounded formula turns forecasts into an operational priority that can be audited and explained line by line. Keeping it separate from the ML makes the decision logic transparent and testable. |
| **Explainability** | Operators will only act on recommendations they understand. Reasons are generated from the same numbers that produced the score. |
| **Rebalancing engine** | Prediction alone does not prevent shortages; an action does. V1 is a transparent greedy optimiser that respects hard safety constraints (donor safe surplus, protected level, distance, district) and escalates what peers cannot cover. V2 (default) keeps those constraints and adds a dynamic donor reserve (uncertainty, velocity, shortage history), a minimum-benefit gate, and lexicographic benefit–cost–safety donor ranking. Its parameters are selected on training-period validation folds (`select_policy.py`), never on the held-out test period. Both policies share one output schema, so the API, UI and simulator can switch between them. |
| **Decision engine** | Joins data, forecasts, anomaly scores, risk and plans into a per-agent snapshot for any decision timestamp, so the dashboard, the API and the simulator share one implementation. |
| **FastAPI service** | Clean, validated, documented contract (`/docs` OpenAPI) between ML and product. Models are loaded once; snapshots are cached per decision time. Structured errors; no stack traces. |
| **Dashboard** | The operations product: Command Center, Agents, Agent Intelligence, Rebalancing Center, Scenario Lab, Impact & Model Health, Responsible AI. All analytics come from the API. |
| **Human review** | Consequential financial actions require an accountable person. Approval requires reviewing evidence and an explicit acknowledgement; it only simulates and is logged. |
| **Impact simulation** | Model accuracy is not business value. Replaying the held-out period under identical demand quantifies shortage events and unmet demand avoided — and the cost (transfers, false alerts, donor risk, logistics). It compares status quo, naive-forecast rebalancing, V1 and V2. A pre-registered rule decides which policy is the default. |
| **Evaluation artifacts** | Machine-readable, reproducible evidence for every number shown in the UI and docs. |

## Runtime view

```
Browser (Next.js, static pages + client fetch)
   │  HTTPS / JSON  (NEXT_PUBLIC_API_URL)
   ▼
FastAPI (uvicorn)  ──  AgentFlowService (singleton)
   │                     ├─ Engine: features (in memory), forecasts for all hours, anomaly scores
   │                     ├─ snapshot cache per decision time
   │                     ├─ rebalancing plan cache
   │                     └─ in-memory simulation audit log
   ▼
ml/models/*.joblib, ml/data/*.parquet, ml/artifacts/*.json
(generated + trained automatically on first start if missing)
```

Start-up loads ~365k rows, builds features and predicts all hours (~10–15 s). Requests are then
served from memory (overview ≈ tens of ms; a new decision time ≈ 0.3 s).

## API

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | liveness, model status, data label |
| GET | `/api/meta/time` | default and available decision times |
| GET | `/api/overview` | KPIs, risk distribution, network trend, top agents, urgent recommendations, districts |
| GET | `/api/agents` | filterable / sortable agent list (risk level, district, cluster, segment, anomaly, search) |
| GET | `/api/agents/{id}` | agent intelligence: liquidity, forecast, risk components, reasons, anomaly drivers, action, 72-h history |
| GET | `/api/agents/{id}/forecast` | forecast and history only |
| GET | `/api/rebalancing/recommendations` | rebalancing plan, escalations, held-for-review; `policy=v1\|v2` (default from the held-out deployment decision) |
| POST | `/api/rebalancing/simulate` | simulate approval of selected recommendations (no state change); optional `policy` |
| GET | `/api/rebalancing/audit` | simulated approvals log |
| POST | `/api/scenario` | demand-shock what-if (network and/or district) |
| GET | `/api/impact` | held-out impact simulation results |
| GET | `/api/model/metrics` | held-out model metrics, training metadata, dataset summary |
| GET | `/api/morning-plan/dates` | Morning Plan demo dates, default date, synthetic/human-review labels |
| GET | `/api/morning-plan?date=` | live Morning Plan: network totals, district conservation proof, agents, flags, explanations, review focus |
| GET | `/api/morning-plan/evidence` | aggregate synthetic research evidence and caveats |
| POST | `/api/morning-plan/simulate` | human-review simulation of a Morning Plan (acknowledgement required; no money moved) |
| GET | `/api/morning-plan/audit` | simulated Morning Plan approvals log |
| GET | `/api/integration-scale` | Phase-2 feed contract summary, replay equivalence and decision-path benchmark (synthetic benchmark evidence) |
| GET | `/api/integration/feed-schema` | JSON Schema of the `agentflow.feed.v1` contract (aggregated agent-hours, no personal data) |

All analytics endpoints accept `as_of` (a held-out hour, 06:00–21:00).

## Morning Liquidity Plan layer (proactive, additive)

The Morning Plan is a separate, additive layer. It does not replace or modify the legacy engine,
the 6-hour forecasts, the risk engine or V1/V2.

```
frozen full-day forecasts (ml/artifacts/morning_plan_demo.json, ~164 KB)
  → apps/api/app/morning_plan.py: live need-first allocator per district
      (fixed cash and e-float budgets, BDT 5,000 floors, integer BDT, agent_id tie-break,
       runtime conservation / floor / no-future-field assertions)
  → /api/morning-plan/* → /morning-plan page → human-review simulation (audit, no money moved)
```

* **Why a fixture?**
  * The full-day models were trained and audited in the research environment (Dual-Liquidity World
    v2, frozen spec `3128176`).
  * Serving pre-computed decision-time forecasts keeps Railway's start-up time and memory unchanged:
    no Dual World dataset is loaded, no training happens at start-up, and no second engine is created.
* **Why recompute the allocation live?** It shows that the predictions are frozen and reproducible,
  while the allocation logic and conservation are enforced in the serving path.
* **Two time scales:**
  * the proactive Morning Plan covers cash and e-float for the whole operating day;
  * reactive intraday V2 rebalancing covers physical cash for the next 6 hours.

See [MORNING_PLAN.md](MORNING_PLAN.md).

## Scalability and integration path

*Implemented in Phase 2 (synthetic benchmark evidence, see [INTEGRATION.md](INTEGRATION.md)):*

* A provider-neutral hourly feed contract (`agentflow.feed.v1`, `ml/agentflow/integration.py`) with strict
  validation and a one-to-one mapping onto `build_features` inputs.
* `StreamingDecisionAdapter`, which keeps a bounded 216-hour window. Its decisions equal the batch
  pipeline in a full chronological replay.
* A measured decision-path benchmark: hourly refresh 2.3 s for 1,000 synthetic agents and 23.6 s for
  10,000 on 4 vCPUs. The main cost is recomputing the whole window every hour.

*Still future work:*

* **Data:** replace `data_gen` with a scheduled extract of hourly per-agent aggregates (amounts and
  counts only — no customer PII) into Parquet / PostgreSQL. `features.build_features` is vectorised
  pandas; for tens of thousands of agents it can move to a warehouse / Spark job keyed by agent and hour.
* **Models:** gradient boosting trains in seconds on 260k rows; a nightly retrain with the same
  time-based evaluation gate is straightforward. Inference for all agents is a single batched call.
* **Serving:** the API is stateless apart from caches and the demo audit log; production would move
  audit logs and approvals to a database and put the service behind authentication / RBAC.
* **Integration:** recommendations could be pushed to an existing distributor / field-officer
  workflow tool via webhook *after* human approval; AgentFlow itself never executes transfers.
* **Rebalancing:** both policies are O(recipients × donors per district) per decision (V2 re-scores candidates per leg, at most 2 legs); a min-cost-flow or
  MILP formulation can replace it behind the same interface if routing constraints are added.
