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

## Phase-2 logistics economics

Phase-1 judge feedback asked us to bring distributor transport and cash-in-transit costs into the
rebalancing loss function. We have no governed upay logistics rates, so Phase 2 adds a transparent,
configurable **synthetic operational-cost proxy** that is ready to accept governed operator rates
without code changes. Details: [docs/EVALUATION.md §9](docs/EVALUATION.md#9-phase-2-logistics-economics-synthetic-operational-cost-proxy).

**What was added**
* One shared module, `ml/agentflow/logistics.py`, used by rebalancing V1, V2 and the impact simulator.
  Every recommended transfer now carries a cost breakdown:

  `total = handling + billable km × per-km cost + (billable km ÷ field speed + handling time) × hourly
  field-officer cost + amount × cash-in-transit bps ÷ 10,000`, where billable km = one-way km × distance
  multiplier (round trip by default). The parts always add up exactly to the total.
* A distributor replenishment proxy for every escalation, measured from a **synthetic distributor hub**
  (the district centroid of the synthetic data generator, not a real distributor location). Missing
  inputs are reported as unavailable, never guessed.
* **Serving default: V2 keeps the proven Phase-1 ranking** (risk points removed per BDT 100 of
  BDT 150 + BDT 25/km). The richer proxy is used to **cost** every recommended transfer and escalation.
  Ranking donors by the proxy (`ranking_cost_model="logistics_proxy"`) is kept as an explicit, labelled
  **experiment that was not adopted**, because it did not improve held-out outcomes (below). Every
  safety rule is unchanged either way.
* `GET /api/logistics/assumptions`, cost fields on every recommendation, escalation and simulation,
  an "Operational cost breakdown" on the Rebalancing page and review drawer, and a Phase-2 card on the
  Impact page. All are labelled *Simulated operational-cost proxy — replace assumptions with governed
  operator rates for deployment.*
* A separately versioned `phase2_logistics` block in `ml/artifacts/impact.json`. **The Phase-1
  `policies` block is unchanged** (V2 there still uses the Phase-1 ranking cost, BDT 150 + BDT 25/km),
  so every Phase-1 number stays auditable.

**Ranking experiment, not adopted (synthetic held-out simulation).** Ranking V2 donors by the richer
proxy changed 13 of 345 transfers and was slightly worse: shortage events 1,223 → 1,229, unmet cash
demand BDT 56,90,940 → BDT 56,99,290 (−40.3% → −40.2% vs status quo), donor shortage events 14 → 15
(unnecessary-transfer share 24.3% → 24.1%). The serving V2 therefore stays on the Phase-1 ranking, and the
default demo plan is unchanged from Phase 1 (14 transfers including RB-013, BDT 4.7 lakh recommended, BDT
5.0 lakh escalated). Costed with the proxy, the serving V2's 345 held-out transfers come to BDT 2,09,482
(BDT 607 each).

**Synthetic assumptions (illustrative demo defaults, not upay or distributor rates):** BDT 100
handling per trip, round trip (×2), BDT 12 per km, 15 km/h average field speed, 15 minutes handling,
BDT 250 per field-officer hour, 10 bps cash-in-transit exposure; distributor trips BDT 150 handling
and ×2. Override any of them with `AGENTFLOW_LOGISTICS_<FIELD>` environment variables (numbers only,
validated; see `.env.example`).

**Still required before production:** governed per-trip, per-km and staff-time rates per district
and vehicle type; real distributor and branch locations and road distances; cash-in-transit insurance
or security rates and limits; field-officer capacity and service windows; then re-selection of V2
parameters on real validation data.

## Phase-2 business impact (synthetic simulated estimate)

Judges asked us to translate technical gains into transaction completion, agent revenue, logistics cost,
customer impact and ROI. `ml/agentflow/business_impact.py` does this as a separate, versioned layer
(`ml/artifacts/business_impact.json`, `GET /api/business-impact`, and a *Business Impact — Synthetic
Simulation* card on the Impact page). Every figure is labelled **Synthetic simulated estimate — not
measured upay performance.** `impact.json` and all Phase-1 and Phase-2 logistics numbers are unchanged.

* **Direct (measured in the simulation):** cash-out value requested / served / unmet, fill rate,
  shortage agent-hours, requested transaction counts, peer transfers, distributor escalations.
* **Estimated:** protected cash-out transactions. The simulator removes BDT, not individual
  transactions, so failed transactions = unmet BDT ÷ the agent-hour's average synthetic ticket, with a
  cluster-ticket cross-check.
* **Assumption-based:** agent commission = protected cash-out value × an illustrative **50 bps** (not
  upay's or any provider's rate; override with `AGENTFLOW_BUSINESS_AGENT_COMMISSION_BPS`). Distributor
  profit is shown only if `AGENTFLOW_BUSINESS_DISTRIBUTOR_FEE_PER_TRIP_BDT` is set; otherwise the
  break-even fee per trip is reported.

V2 (the serving Phase-1-ranked plan) over the 14 held-out days, against the status quo: **BDT 38.5
lakh** of cash-out served that was unmet, **≈ 2,466 estimated transactions** protected (range
2,438–2,466), 794 fewer shortage agent-hours, 345 peer transfers and 154 distributor agent-day trips. At
50 bps the illustrative commission protected (BDT 19,230) does **not** cover the peer logistics cost proxy
(BDT 2,09,482); break-even needs about 545 bps. The logistics-ranked experiment is reported separately
and never mixed into these figures. A small sensitivity grid (25–200 bps × 0.5–1.5× cost) stays negative throughout. The case rests on
customers served and on cheaper delivery (V2: BDT 85 of logistics per protected transaction vs BDT 116
for V1). **No ROI is claimed**, because one would need retention, lifetime-value or provider-revenue data
that a synthetic prototype does not have. Details: [docs/EVALUATION.md §10](docs/EVALUATION.md#10-phase-2-business-impact-synthetic-simulated-estimate).

## Phase-2 security, approval and manipulation guardrails

Prototype controls that answer the judges' security gaps. **They are not enterprise IAM or banking-grade
infrastructure.** Details: [docs/SECURITY.md](docs/SECURITY.md).

* **Server-enforced approval:** intraday `POST /api/rebalancing/simulate` requires
  `reviewer_acknowledged: true` (strict boolean), like the Morning Plan endpoint. Bypassing the dashboard
  does not bypass the check.
* **Replay guard:** the same approval submitted twice returns the original audit record (`replayed: true`).
* **Rate limiting:** process-local sliding window on the two simulation endpoints only (default 20 per
  60 s per client; HTTP 429 with `Retry-After`). Dashboard reads are never limited.
* **Tamper-evident audit:** SHA-256 hash chain (`previous_hash`, `record_hash`) over every simulated
  approval, verified before each write; a broken chain blocks new approvals. Optional append-only JSONL file
  via `AGENTFLOW_AUDIT_LOG_PATH`, re-verified at start-up. Durability across containers needs a persistent
  volume or an external governed audit store.
* **Manipulation guardrail:** tests show that a manufactured transaction surge on an at-risk agent is
  flagged ANOMALOUS by the unchanged Phase-1 detector and then held for review with no peer liquidity.
  Anomaly is never labelled fraud. Limitations: milder manipulation can stay below the thresholds, and
  WATCH-level agents are not held.
* **Authentication:** not implemented; no secret is exposed to the browser. Enterprise identity and
  role-based approval remain production requirements.

## Phase-2 integration & scale (synthetic benchmark evidence)

**Synthetic benchmark evidence — not real upay production performance, and not a real upay integration.**
Details: [docs/INTEGRATION.md](docs/INTEGRATION.md). No Kafka, WebSockets, database or new models were added.

* **Feed contract `agentflow.feed.v1`:** one aggregated record per agent per hour (balances, cash-in/out
  counts and amounts, requested vs served cash-out, send-money/payment counts) plus an agent registry.
  There is no personal data. Validation is strict: unknown and personal-data-like fields are rejected,
  timestamps must be hour-aligned, amounts finite and non-negative, counts integer, served ≤ requested,
  and invalid batches are rejected whole. The contract maps one-to-one onto the existing pipeline inputs;
  its JSON Schema is at `GET /api/integration/feed-schema`.
* **Replay = batch pipeline:** the stored synthetic dataset was replayed hour by hour through the contract
  (1,814 hours, 362,800 events). At four held-out timestamps, including the default demo time, the
  streamed decision snapshot matches `Engine.load(serving=True)` for all 200 agents, with identical
  risk, anomaly and review decisions and a maximum numeric difference of 0.0. The replay is deterministic.
* **Decision-path benchmark** (one hourly refresh = validate, features, forecast + anomaly inference, risk
  snapshot, V1 + V2 plans; median of 3; 4 vCPUs): 200 agents 0.61 s · 1,000 agents 2.3 s · 5,000 agents
  12.0 s · 10,000 agents 23.6 s, with peak memory 1.9 GB at 10,000.
* **Bottleneck (honest):** the existing engine recomputes features and model scores for the whole 216-hour
  window every refresh (about 80% of the time at 10,000 agents). Incremental caching is not implemented.
  The V2 transfer search is a Python loop that grows roughly linearly or slightly faster.
* Evidence: `ml/artifacts/integration_scale.json` (`phase2-integration-1`), `GET /api/integration-scale`,
  and the **Integration & Scale** card on the Impact page. Reproduce with `python ml/scripts/integration_scale.py`.

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
* **Quality:** pytest (225 tests), ESLint, `tsc`, GitHub Actions CI

## Repository structure

```
agentflow-ai/
  apps/
    api/app/          FastAPI service (main.py routes, schemas.py, service.py, morning_plan.py)
    web/src/          Next.js dashboard (app/ pages, components/, lib/)
  ml/
    agentflow/        data_gen, features, forecast, anomaly, risk, rebalance (V1), rebalance_v2, policy_selection, impact, engine, evaluation, integration
    scripts/          generate_data.py, train.py, evaluate.py, run_pipeline.py, integration_scale.py; research/ (Morning Plan fixture builder)
    artifacts/        metrics.json, impact.json, training_metadata.json, dataset_summary.json,
                      morning_plan_demo.json, morning_plan_evidence.json, integration_scale.json (committed)
    data/ models/     generated data and model binaries (git-ignored, reproducible)
  docs/               ARCHITECTURE, DATA_CARD, MODEL_CARD, EVALUATION, DEMO_SCRIPT, PROJECT_REPORT, TEAM_BRIEFING, SECURITY, MORNING_PLAN, INTEGRATION
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
# optional, separate (wall-clock timings vary run to run):
python ml/scripts/integration_scale.py   # feed-contract replay equivalence + scale benchmark -> integration_scale.json (~3 min)
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
| `AGENTFLOW_BUSINESS_AGENT_COMMISSION_BPS` / `AGENTFLOW_BUSINESS_DISTRIBUTOR_FEE_PER_TRIP_BDT` | API / ML | 50 / unset | illustrative business-impact rates (numbers only; synthetic simulated estimate) |
| `AGENTFLOW_RATE_LIMIT_SIMULATIONS` / `AGENTFLOW_RATE_LIMIT_WINDOW_SECONDS` | API | 20 / 60 | prototype rate limit on simulation endpoints (0 disables) |
| `AGENTFLOW_RATE_LIMIT_TRUST_FORWARDED_FOR` | API | off | `1` = key clients by X-Forwarded-For (only behind a trusted proxy) |
| `AGENTFLOW_AUDIT_LOG_PATH` | API | unset (in memory) | optional append-only JSONL file for the tamper-evident simulation audit |
| `AGENTFLOW_LOGISTICS_<FIELD>` | API / ML | synthetic demo values | override one logistics-cost assumption, e.g. `AGENTFLOW_LOGISTICS_CASH_IN_TRANSIT_BPS=10` (numbers only) |

## Testing and build

```bash
python -m pytest -q                       # from repo root: 225 tests (data, leakage, models, risk, rebalancing V1/V2, logistics cost proxy, business impact, security safeguards, gaming guardrails, feed contract + replay equivalence + benchmark artifact, policy selection, impact, API, contract, Morning Plan)
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
* Integration & scale evidence is synthetic: a deterministic file replay through the feed contract (no live ledger, broker or real upay integration) and a single-container benchmark. Each hourly refresh recomputes the full 216-hour window (no incremental cache), so cost grows roughly linearly with agents (23.6 s at 10,000 synthetic agents).
* The audit log is tamper-evident but in memory by default (optional JSONL file on a persistent volume); rate limiting is process-local; there is no authentication (out of scope for the prototype).
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
