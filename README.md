# AgentFlow AI

**Explainable Predictive Liquidity Orchestration for MFS Agent Networks**

> **Predict. Explain. Rebalance.**

AgentFlow predicts where an MFS agent may run short of liquidity before customers are affected,
explains why, and recommends a safe, human-reviewed rebalancing action.

Built for the **AI DEV FEST 2026 AI Hackathon** organised by **DIU CPC × upay**.

> ⚠️ **Synthetic data for hackathon prototyping — not production upay data.**
> AgentFlow is a decision-support prototype. It never moves real money: approvals only run simulations.

---

## Results at a glance (synthetic held-out evaluation, last 14 days, never used in training)

| | Result |
|---|---|
| Cash-demand forecast (next 6 h) | MAE **BDT 6,138** vs. 9,691 naive (−36.7%) and 7,890 seasonal baseline (**−22.2%**) |
| Peak cash-requirement forecast | MAE BDT 5,147 vs. 5,524 seasonal (−6.8%), RMSE −12.7%; P90 band coverage **89.5%** (nominal 90%) |
| Risk early warning (HIGH+ alerts → shortage within 6 h) | precision **81.5%**, recall 41.7%, ROC-AUC **0.935** (vs. 0.911 when fed naive forecasts) |
| Behavioural anomaly detection | ROC-AUC **0.981**, average precision 0.671 on injected anomalies |
| **Business impact** (same demand, same total cash) | shortage events **−37.8%**, unmet cash demand **−38.9% (BDT 37.1 lakh avoided)**, service availability 96.76% → **97.92%** |

Every number is produced by `python ml/scripts/run_pipeline.py` and stored in
[`ml/artifacts/`](ml/artifacts/); a fresh clone reproduces them byte-for-byte. Full details and
trade-offs (false alerts, donor risk, group differences): [docs/EVALUATION.md](docs/EVALUATION.md).

---

## Problem

Mobile Financial Services agents need physical cash to serve cash-out and electronic float to serve
cash-in. Demand shifts by hour, weekday, salary period and local events. When an agent's drawer
runs dry, customers are turned away, the agent loses income and operations teams rebalance
reactively, often after the damage is done. Static daily provisioning cannot anticipate a
salary-day afternoon rush in a garment-worker neighbourhood or a rural market day.

We frame this as a **future-ready MFS capability**; we make no claim about upay's current
operations.

## Solution — the complete intelligence loop

```
FORECAST → RISK → EXPLAIN → RECOMMEND → HUMAN REVIEW → SIMULATE → MEASURE IMPACT
```

AgentFlow does not stop at prediction. It converts a prediction into an explainable, safe and
measurable operational recommendation:

1. **What is likely to happen?** ML forecasts each agent's next-6-hour cash-out demand and the
   *peak cash requirement* (max cumulative net cash drain), with a P90 uncertainty band.
2. **Why?** A transparent 0–100 risk score with five bounded components and evidence-based reasons
   ("Current cash of BDT 20,640 covers about 53% of the forecast requirement…").
3. **What should operations consider doing?** A constrained optimiser recommends peer rebalancing
   from nearby LOW-risk agents who keep ≥ 110% of their own P90 requirement, escalates the rest to
   the distributor, and holds agents with unusual activity for manual review.
4. **What improves?** A held-out simulation measures shortage events, unmet demand and service
   availability with and without AgentFlow.

## Product

| Page | What it shows |
|---|---|
| **Command Center** | Active / at-risk / critical agents, projected service readiness (now and after the recommended plan), 6-h forecast demand, recommended rebalancing value, 48-h forecast-vs-actual trend, risk distribution, top at-risk agents, urgent recommendations, district overview |
| **Agents** | Sortable, filterable table (risk level, behaviour, district, location cluster, volume segment, search) |
| **Agent Intelligence** | Current cash, 6-h forecasts (P50/P90), expected gap, risk score with component breakdown, *Why this risk?* (with a deterministic **বাংলায় ব্যাখ্যা করুন** Bangla toggle), recommended action, behavioural drivers, 72-h history, model evidence |
| **Rebalancing Center** | Recommendations with source/destination reserves and risk before/after → **Review Recommendation** → evidence drawer → acknowledgement → **Approve Simulation** → portfolio before/after + audit log; escalations and held-for-review lists |
| **Scenario Lab** | Network (+10/25/40%) and district demand shocks; risk, shortfall, rebalancing and escalation recomputed live |
| **Impact & Model Health** | Without vs. with AgentFlow (and naive-forecast rebalancing), daily unmet demand, group breakdown, baseline vs. ML metrics, feature importance, alert precision/recall, anomaly metrics, fairness checks |
| **Responsible AI** | Privacy, explainability, oversight, safety constraints, anomaly ≠ fraud, limits of trust |

A decision-time selector (top bar) lets you replay any hour of the held-out period.

## AI / ML approach

| Component | Approach |
|---|---|
| Features | 31 leakage-safe features: calendar, agent attributes, lags, rolling stats, same-window history, velocity |
| Baselines | same window yesterday; 7-day same-window average |
| Forecasting | scikit-learn `HistGradientBoostingRegressor` (Poisson / squared error) + 0.9-quantile model |
| Anomaly detection | Isolation Forest + robust deviation rule (hybrid, percentile-averaged) on agent-relative surges |
| Risk engine | deterministic, monotone, bounded formula (coverage, P90 tail, shortfall, velocity, history) |
| Rebalancing | greedy constrained optimiser (same district, ≤ 15 km, donor safe surplus, protected level) |
| Impact | hour-by-hour held-out replay of three policies with identical exogenous demand |

No LLM is used in the decision path; the core system has no external API dependency.

## Synthetic-data strategy

200 agents × 76 days × hourly (364,800 rows) across 8 districts, 3 location clusters and 3 volume
segments, generated with a fixed seed. Injected structure: daily cycles, Bangladesh weekend,
salary-period uplift, rural market days, AR(1) demand regimes, local spikes, noise, a static
status-quo cash policy that produces realistic shortages, and 426 labelled behavioural anomaly
episodes. No PII. See [docs/DATA_CARD.md](docs/DATA_CARD.md).

## Architecture

```
Synthetic data → Feature engineering → Forecast models ┐
                                      → Anomaly model   ┴→ Risk engine → Explainability
→ Rebalancing engine → FastAPI → Next.js dashboard → Human review → Simulation → Impact evaluation
```

Details and rationale for each layer: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Technology stack

* **ML / data:** Python 3.11, pandas, NumPy, scikit-learn, PyArrow, joblib
* **API:** FastAPI, Pydantic v2, Uvicorn
* **Frontend:** Next.js 15 (App Router), React 19, TypeScript, Tailwind CSS 4, Recharts, lucide-react
* **Quality:** pytest (49 tests), ESLint, `tsc`, GitHub Actions CI

## Repository structure

```
agentflow-ai/
  apps/
    api/app/          FastAPI service (main.py routes, schemas.py, service.py)
    web/src/          Next.js dashboard (app/ pages, components/, lib/)
  ml/
    agentflow/        data_gen, features, forecast, anomaly, risk, rebalance, impact, engine, evaluation
    scripts/          generate_data.py, train.py, evaluate.py, run_pipeline.py
    artifacts/        metrics.json, impact.json, training_metadata.json, dataset_summary.json (committed)
    data/ models/     generated data and model binaries (git-ignored, reproducible)
  docs/               ARCHITECTURE, DATA_CARD, MODEL_CARD, EVALUATION, DEMO_SCRIPT, PROJECT_REPORT
  tests/              data, forecast, risk/anomaly, rebalancing, impact, API, contract tests
  .github/workflows/  CI
```

## Getting started

Prerequisites: **Python 3.11+**, **Node.js 20+**.

```bash
git clone https://github.com/ariful-arif-232/agentflow-ai.git
cd agentflow-ai
pip install -r requirements.txt
```

### 1. Generate data, train and evaluate (≈ 1 minute)

```bash
python ml/scripts/run_pipeline.py
# or step by step:
python ml/scripts/generate_data.py   # synthetic dataset -> ml/data/
python ml/scripts/train.py           # models -> ml/models/
python ml/scripts/evaluate.py        # metrics.json + impact.json -> ml/artifacts/
```

(The API also runs generation + training automatically on first start if artifacts are missing.)

### 2. Run the backend

```bash
cd apps/api
uvicorn app.main:app --port 8000
# health check: http://localhost:8000/health   ·   OpenAPI docs: http://localhost:8000/docs
```

### 3. Run the frontend

```bash
cd apps/web
npm install
npm run dev            # http://localhost:3000
```

### Environment variables

Copy `.env.example` and adjust as needed (no secrets are required):

| Variable | Used by | Default | Purpose |
|---|---|---|---|
| `AGENTFLOW_CORS_ORIGINS` | API | `http://localhost:3000` | comma-separated allowed browser origins |
| `AGENTFLOW_AS_OF` | API | `2026-08-31T13:00` | default decision time |
| `NEXT_PUBLIC_API_URL` | web | `http://localhost:8000` | API base URL seen by the browser |

## Testing and build

```bash
python -m pytest -q                       # from repo root: 49 tests (data, leakage, models, risk, rebalancing, impact, API, contract)
cd apps/web && npm run lint && npm run typecheck && npm run build
```

CI runs the full pipeline, backend tests and frontend lint / typecheck / build on every push.

## Demo

A 3–5 minute walkthrough is in [docs/DEMO_SCRIPT.md](docs/DEMO_SCRIPT.md). Short version (decision
time Mon 31 Aug 13:00): Command Center → agent **AG-0171** (BDT 20,640 cash vs. BDT 38,675 forecast
requirement, HIGH) → *Why this risk?* → Rebalancing Center → review **RB-019** → Approve Simulation →
Impact page.

## Deployment

| Component | URL | Platform |
|---|---|---|
| Dashboard | https://agentflow-ai-nine.vercel.app | Vercel (root directory `apps/web`, `NEXT_PUBLIC_API_URL` set to the API) |
| API | https://agentflow-api-production.up.railway.app (`/health`, `/docs`) | Railway (root `Dockerfile`; data generation + training run at image build) |

Both redeploy automatically on every push to `main`. The API reads `AGENTFLOW_CORS_ORIGINS` for the
allowed dashboard origins. Everything also runs locally with the commands above.

## Responsible AI

* **Privacy:** synthetic data only; PII absence is tested.
* **Explainability:** deterministic risk formula; every reason generated from computed evidence; source tags in the UI.
* **Human oversight:** recommendations require review and explicit acknowledgement; approval only simulates and is audit-logged.
* **Safety:** donors keep ≥ 110% of their P90 requirement, amounts never exceed safe surplus, no negative balances (tested).
* **Anomaly ≠ fraud:** unusual activity triggers manual review, never an automated label or liquidity score change.
* **Security:** env-based config, `.env` git-ignored, strict validation, structured errors without stack traces, configurable CORS, no code execution from input.
* **Honest evaluation:** time-based purged split, baselines, reported weaknesses.

## Known limitations

* Synthetic data; results demonstrate the method, not real-world upay performance.
* Peak-requirement forecast improves on a strong seasonal baseline only modestly (−6.8% MAE).
* HIGH+ alerts catch ~42% of shortage windows; sudden spikes remain hard to anticipate.
* ~21% of simulated transfers were not strictly needed; 25 donor shortage events in 501 transfers.
* Simulator assumes exogenous demand, 1-hour transfers and simple costs; e-float not binding.
* Audit log is in memory (resets when the API restarts); no authentication (out of scope for the prototype).

## Future real-data validation path

1. Extract hourly per-agent aggregates (amounts and counts only; no customer data), including declined cash-out attempts.
2. Re-run the unchanged pipeline; compare against baselines with the same time-based split.
3. Back-test the impact simulator against historical rebalancing logs and distributor constraints.
4. Shadow-mode pilot: recommendations shown to operations staff, decisions recorded, no automation.
5. Monitor forecast error, P90 coverage, alert precision/recall and group consistency continuously.

## AI tool disclosure

This project was developed with AI-assisted development tools, including Claude Code, under the
direction and review of the participant, who is responsible for the final submission. The product
itself does not use a generative AI model in its decision path.

## License

Hackathon prototype — all rights reserved by the author unless a license file is added.
