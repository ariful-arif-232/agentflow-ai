# AgentFlow AI

**Explainable Predictive Liquidity Orchestration for MFS Agent Networks**

> **Same liquidity. Placed ahead of demand.**

AgentFlow forecasts where MFS agents will need liquidity and recommends placing the **same** working
capital ahead of demand. Each morning it plans physical cash and e-float. During the day it monitors
cash pressure, explains the risk and recommends safe, human-reviewed peer recovery. It never moves
real money. See [Two time scales](#two-time-scales-proactive-and-reactive).

Built for the **AI DEV FEST 2026 AI Hackathon** (Track 05: Merchant & Agent Intelligence — Agent Liquidity Forecasting) organised by **DIU CPC × upay** by a registered
3-member team. Engineering was carried out by one primary implementer, and the development workflow
is organised around that. Teammate briefing: [docs/TEAM_BRIEFING.md](docs/TEAM_BRIEFING.md).

> ⚠️ **Synthetic data for hackathon prototyping — not production upay data.**
> AgentFlow is a decision-support prototype. It never moves real money: approvals only run simulations.

---

## Results at a glance: intraday system (synthetic held-out evaluation, last 14 days, never used in training)

These results come from the legacy intraday environment, where e-float is tracked but is not a
binding constraint. The Morning Plan is evaluated separately (see below).

| | Result |
|---|---|
| Cash-demand forecast (next 6 h) | MAE **BDT 6,138** vs. 9,691 naive (−36.7%) and 7,890 seasonal baseline (**−22.2%**) |
| Peak cash-requirement forecast | MAE BDT 5,147 vs. 5,524 seasonal (−6.8%), RMSE −12.7%; P90 band coverage **89.5%** (nominal 90%) |
| Risk early warning (HIGH+ alerts → shortage within 6 h) | precision **81.5%**, recall 41.7%, ROC-AUC **0.935** (vs. 0.911 when fed naive forecasts) |
| Behavioural anomaly detection | ROC-AUC **0.981**, average precision 0.671 on injected anomalies |
| **Business impact, rebalancing policy V2 (default)** (same demand, same total cash) | shortage events **−39.4%**, unmet cash demand **−40.3% (BDT 38.5 lakh avoided)**, service availability 96.76% → **97.95%**, with 345 transfers, 14 donor shortage events and BDT 1.15 lakh logistics cost |
| Business impact, original policy V1 | shortage events −37.8%, unmet cash demand −38.9% (BDT 37.1 lakh avoided), 501 transfers, 25 donor shortage events, BDT 1.58 lakh logistics cost |

Every number is produced by `python ml/scripts/run_pipeline.py` and stored in
[`ml/artifacts/`](ml/artifacts/). With the pinned project environment (`requirements.txt` and the
Docker base-image digest), the evaluated decision outputs, business-impact metrics and demo values
reproduce. Runtime `fit_seconds` metadata is excluded, and tiny cross-machine floating-point variation
may occur in internal anomaly thresholds. Full details and trade-offs (false alerts, donor risk,
group differences): [docs/EVALUATION.md](docs/EVALUATION.md).

---

## Problem

> For MFS liquidity operations teams, agents running short of physical cash or e-float during demand
> peaks can cause failed customer transactions and lost agent income. AgentFlow uses per-agent
> transaction-flow aggregates to forecast liquidity need and recommend human-reviewed placement
> decisions, with success measured by unmet demand under the same working-capital budget.

Mobile Financial Services agents need physical cash to serve cash-out and electronic float to serve
cash-in. Demand shifts by hour, weekday, salary period and local events. When an agent's drawer
runs dry, customers are turned away, the agent loses income and operations teams rebalance
reactively, often after the damage is done. Static daily provisioning cannot anticipate a
salary-day afternoon rush in a garment-worker neighbourhood or a rural market day.

We frame this as a **future-ready MFS capability**; we make no claim about upay's current
operations.

## Solution — the intraday intelligence loop (*Predict. Explain. Rebalance.*)

```
FORECAST → RISK → EXPLAIN → RECOMMEND → HUMAN REVIEW → SIMULATE → MEASURE IMPACT
```

During the day, AgentFlow does not stop at prediction. It converts a 6-hour cash prediction into an
explainable, safe and measurable operational recommendation:

1. **What is likely to happen?** ML forecasts each agent's next-6-hour cash-out demand and the
   *peak cash requirement* (max cumulative net cash drain), with a P90 uncertainty band.
2. **Why?** A transparent 0–100 risk score with five bounded components and evidence-based reasons
   ("Current cash of BDT 20,640 covers about 53% of the forecast requirement…").
3. **What should operations consider doing?** A constrained optimiser recommends peer rebalancing
   from nearby LOW-risk agents, escalates the rest to the distributor, and holds agents with unusual
   activity for manual review. The default **Policy V2** only proposes transfers that materially reduce
   the recipient's risk. It protects donors with a dynamic reserve (forecast uncertainty, velocity,
   shortage history) and ranks donors by benefit, safety and logistics cost. The original nearest-donor
   **Policy V1** remains selectable for comparison.
4. **What improves?** A held-out simulation measures shortage events, unmet demand and service
   availability with and without AgentFlow.

### Two time scales: proactive and reactive

**Same liquidity. Placed ahead of demand.**

| | What AgentFlow does |
|---|---|
| **Morning** (07:00 → 08:00) | Predict each agent's **full-day** (08:00–23:59) physical-cash *and* e-float requirement, then recommend where the **same** district working capital should sit before demand arrives (the Morning Liquidity Plan) |
| **Intraday** (hourly) | Monitor 6-hour **cash** pressure, explain the risk and recommend safe **V2** peer recovery (*Predict. Explain. Rebalance.*) |
| **Human** | Reviews and acknowledges every consequential action. Approval only runs a simulation. |
| **Measure** | Each environment is evaluated separately, and the results are never combined |

The two layers are evaluated in **two separate synthetic environments**. They are not one combined
simulation:
* **Intraday (V1/V2):** the legacy environment. E-float is tracked but is not a binding constraint;
  cash-in is never declined.
* **Morning Plan:** the separate Dual-Liquidity World v2. Physical cash **and** e-float are both
  binding: cash-out fails when cash runs out, and cash-in fails when e-float runs out.

**Morning Plan evidence.** In fresh synthetic worlds from the same world family, the frozen full-day
ML policy reduced combined unmet demand by a median **20.6%** versus the strongest cautious historical
baseline (7-day q90), while conserving each district's cash and e-float budgets exactly. **This is
synthetic held-out evidence, not measured upay performance, and not an expected saving for the date
shown in the demo.**

* **Success bar.** The protocol and success bar were committed before the audit seeds (2036–2040)
  were generated. ML had to:
  * match or beat both the q90 and the 7-day-max rule in at least 4 of 5 worlds;
  * reach a median combined-unmet reduction of at least 5% against the better of the two;
  * worsen cash or e-float unmet by more than 5% in at most 1 world;
  * conserve both budgets exactly.

  All five checks passed.
* **Absolute example (audit world seed 2036: 200 agents, 14 held-out operating days, 08:00–23:59).**
  Combined unmet demand fell from about BDT 49.7 lakh under the q90 rule to about BDT 40.8 lakh under
  the frozen ML (−17.9% in this world). Cash-out fill rose from 99.65% to 99.80%.

Details, research path and caveats: [docs/MORNING_PLAN.md](docs/MORNING_PLAN.md).

**Who moves the liquidity?** Nobody, in this prototype. AgentFlow only recommends target levels and
simulates approval; it never executes a financial transfer. A future deployment could hand *approved*
target levels to an existing distributor, field-officer or bank-deposit replenishment workflow.
Whether such targets can be changed daily is a real-world validation question.

**How we got there.** For every step, the protocol and success bar were committed before results were
computed, and the negative results are kept:
1. naive peer cash/e-float swaps were rejected because local complementarity was sparse
   (development seeds 2026–2030);
2. the 6-hour ML was rejected for morning planning because seasonal full-day history beat it (same
   seeds);
3. the prediction horizon was then aligned to the actual full-day decision. A full-day ML beat the
   7-day mean on confirmatory seeds 2031–2035, whose protocol was committed before they were
   generated;
4. the final frozen model survived the cautious-baseline (historical q90/max) attribution on audit
   seeds 2036–2040.

## Product

| Page | What it shows |
|---|---|
| **Command Center** | Active / at-risk / critical agents, projected service readiness (now and after the recommended plan), 6-h forecast demand, recommended rebalancing value, 48-h forecast-vs-actual trend, risk distribution, top at-risk agents, urgent recommendations, district overview |
| **Morning Plan** | Proactive full-day cash + e-float positioning with the same working capital. Before/after totals match exactly (BDT 0 extra). Shows cash and e-float plans, a review focus (largest cuts, low-volume cuts, rural e-float reductions), a sortable agent table with an explanation drawer, a district conservation proof, **Approve Simulation**, and historical research evidence with caveats. |
| **Agents** | Sortable, filterable table (risk level, behaviour, district, location cluster, volume segment, search) |
| **Agent Intelligence** | Current cash, 6-h forecasts (P50/P90), expected gap, risk score with component breakdown, *Why this risk?* (with a deterministic **বাংলায় ব্যাখ্যা করুন** Bangla toggle), recommended action, behavioural drivers, 72-h history, model evidence |
| **Rebalancing Center** | V2 (default) / V1 policy toggle; recommendations with source/destination reserves, risk before/after and V2 evidence (expected recipient benefit, donor margin above its dynamic reserve) → **Review Recommendation** → evidence drawer → acknowledgement → **Approve Simulation** → portfolio before/after + audit log; escalations and held-for-review lists |
| **Scenario Lab** | Network (+10/25/40%) and district demand shocks; risk, shortfall, rebalancing and escalation recomputed live |
| **Impact & Model Health** | Policy comparison (without AgentFlow / naive forecast / V1 / V2) with safety and efficiency metrics, daily unmet demand, group breakdown, baseline vs. ML metrics, feature importance, alert precision/recall, anomaly metrics, fairness checks |
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
| Rebalancing | V1: greedy nearest-donor optimiser (same district, ≤ 15 km, donor safe surplus, protected level). V2 (default): the same constraints plus a dynamic donor reserve, minimum-benefit gate and benefit–cost–safety donor ranking, with parameters selected on training-period validation folds |
| Impact | hour-by-hour held-out replay of four policies (status quo, naive-forecast rebalancing, AgentFlow V1, AgentFlow V2) with identical exogenous demand |
| Morning Plan (proactive) | frozen full-day `HistGradientBoostingRegressor` P50/P90 forecasts of cash and e-float requirements (research spec `3128176`), served from a compact synthetic fixture; deterministic need-first allocator with fixed district budgets, BDT 5,000 floors and exact conservation, recomputed live |

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

Proactive layer (separate, additive):
frozen full-day forecasts (compact JSON fixture) → live district-constrained allocator → /api/morning-plan → Morning Plan page → human-review simulation
```

Details and rationale for each layer: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Technology stack

* **ML / data:** Python 3.11, pandas, NumPy, scikit-learn, PyArrow, joblib
* **API:** FastAPI, Pydantic v2, Uvicorn
* **Frontend:** Next.js 15 (App Router), React 19, TypeScript, Tailwind CSS 4, Recharts, lucide-react
* **Quality:** pytest (103 tests), ESLint, `tsc`, GitHub Actions CI

## Repository structure

```
agentflow-ai/
  apps/
    api/app/          FastAPI service (main.py routes, schemas.py, service.py, morning_plan.py)
    web/src/          Next.js dashboard (app/ pages, components/, lib/)
  ml/
    agentflow/        data_gen, features, forecast, anomaly, risk, rebalance (V1), rebalance_v2, policy_selection, impact, engine, evaluation
    scripts/          generate_data.py, train.py, evaluate.py, run_pipeline.py; research/ (Morning Plan fixture builder)
    artifacts/        metrics.json, impact.json, training_metadata.json, dataset_summary.json,
                      morning_plan_demo.json, morning_plan_evidence.json (committed)
    data/ models/     generated data and model binaries (git-ignored, reproducible)
  docs/               ARCHITECTURE, DATA_CARD, MODEL_CARD, EVALUATION, DEMO_SCRIPT, PROJECT_REPORT, TEAM_BRIEFING, SECURITY, MORNING_PLAN
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

### 1. Generate data, train, select the rebalancing policy and evaluate (≈ 4 minutes)

```bash
python ml/scripts/run_pipeline.py
# or step by step:
python ml/scripts/generate_data.py   # synthetic dataset -> ml/data/
python ml/scripts/train.py           # models -> ml/models/
python ml/scripts/select_policy.py   # V2 parameters on training-period validation folds -> policy_selection.json
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
python -m pytest -q                       # from repo root: 103 tests (data, leakage, models, risk, rebalancing V1/V2, policy selection, impact, API, contract, Morning Plan)
cd apps/web && npm run lint && npm run typecheck && npm run build
```

CI runs the full pipeline, backend tests and frontend lint / typecheck / build on every push.

## Demo

Demo scripts (90 s / 3 min / 5 min), an API-failure plan and judge Q&A are in
[docs/DEMO_SCRIPT.md](docs/DEMO_SCRIPT.md). In the app, **Reset demo** restores the default snapshot
(client-side only), **Judge demo** shows a six-step guide with live values, and if the API is
unreachable the app shows a clear *"Live decision service is temporarily unavailable"* message with
**Retry**. It never shows cached numbers as live. Short version (decision
time Mon 31 Aug 13:00): Command Center → **Morning Plan** (proactive full-day positioning, same working
capital) → agent **AG-0171** (BDT 20,640 cash vs. BDT 38,675 forecast
requirement, HIGH) → *Why this risk?* → Rebalancing Center (policy V2) → review **RB-013** → Approve
Simulation → Impact page policy comparison.

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

Security & prototype threat model: [docs/SECURITY.md](docs/SECURITY.md)

## Known limitations

* Synthetic data; results demonstrate the method, not real-world upay performance.
* Peak-requirement forecast improves on a strong seasonal baseline only modestly (−6.8% MAE).
* HIGH+ alerts catch ~42% of shortage windows; sudden spikes remain hard to anticipate.
* Policy V2: 24.3% of its 345 simulated transfers were not strictly needed (V1: 21.4% of 501), and there
  were still 14 donor shortage events (V1: 25). V2 is slightly worse than V1 for rural agents.
* The intraday simulator assumes exogenous demand, 1-hour transfers and simple costs. In this legacy
  environment, e-float is tracked but is not a binding constraint. Only the separate Morning Plan
  environment treats e-float as binding.
* Audit log is in memory (resets when the API restarts); no authentication (out of scope for the prototype).
* **Morning Plan:**
  * The demo is a synthetic fixture (one world, 14 dates), and its evidence comes from the same
    synthetic world family.
  * Cash P90 coverage is about 85%, against a nominal 90%.
  * Low-volume agents did worse than a cautious q90 rule in 4 of 5 audit worlds.
  * Rural e-float allocations can fall materially.
  * Morning repositioning is assumed free and instantaneous.
  * Real-data shadow validation is required before any deployment.

## Future real-data validation path

1. Extract hourly per-agent aggregates (amounts and counts only; no customer data), including declined cash-out attempts.
2. Re-run the unchanged pipeline; compare against baselines with the same time-based split.
3. Back-test the impact simulator against historical rebalancing logs and distributor constraints.
4. Shadow-mode pilot: recommendations shown to operations staff, decisions recorded, no automation.
5. Monitor forecast error, P90 coverage, alert precision/recall and group consistency continuously.

## AI tool disclosure

This project was developed with AI-assisted development tools, including Claude Code, under the
direction and review of the team's primary implementer. The registered team is responsible for the
final submission. The product
itself does not use a generative AI model in its decision path.

## License

Hackathon prototype — all rights reserved by the registered team unless a license file is added.
