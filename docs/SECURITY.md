# Security & Prototype Threat Model — AgentFlow AI

AgentFlow AI is a **decision-support prototype** for MFS agent networks (AI DEV FEST 2026, Track 05: Merchant & Agent Intelligence — Agent Liquidity Forecasting),
built on **synthetic data, not real upay data**. It never moves money: approving a recommendation
only runs a simulation. This document states what is protected today, what is not, and what a
production version would need. It is not a claim of production readiness.

---

## A. Controls implemented today (verified in code)

| Area | Control | Where |
|---|---|---|
| Data privacy | Synthetic data only, generated from a fixed seed; no names, phone numbers, NIDs or customer records. PII absence is tested. | `ml/agentflow/data_gen.py`, `tests/test_data.py::test_no_real_pii_columns_or_values` |
| Input validation | Pydantic v2 request models reject unknown fields (`extra="forbid"`). Recommendation lists are limited to 1–100 IDs, reviewer notes to 500 characters and scenario shocks to −30..80% / 0..100%. Policy accepts only `v1`/`v2`. | `apps/api/app/schemas.py` |
| Identifier checks | `agent_id` must match `AG-\d{4}`; recommendation IDs must match `RB-\d{3}`; agent search is pattern-restricted; enum query parameters are `Literal` types. `as_of` must be an hour inside the held-out window. Unknown scenario districts are rejected. | `apps/api/app/main.py`, `apps/api/app/service.py` |
| Error handling | Every error returns `{"error": {"code", "message"}}`. Unhandled exceptions are logged server-side and return a generic `"An internal error occurred."`, with no stack trace in responses (tested). | `apps/api/app/main.py`, `tests/test_api.py` |
| CORS | Allowed origins come from `AGENTFLOW_CORS_ORIGINS` (default `http://localhost:3000`); methods are limited to GET/POST, headers to `Content-Type`, and credentials are disabled. | `apps/api/app/main.py` |
| Secrets | `.env` and `.env.*` are git-ignored; `.env.example` contains placeholders only. No secret is required to run the prototype. | `.gitignore`, `.env.example` |
| Web headers | `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY` and `Referrer-Policy: strict-origin-when-cross-origin` are set, and the `X-Powered-By` header is disabled. | `apps/web/next.config.ts` |
| Container | The API image runs as a non-root user (`agentflow`, uid 10001). | `Dockerfile` |
| No code execution from input | Request data is never evaluated, executed or used to build shell commands or file paths. | `apps/api/app/` |
| Deterministic decisions | The risk score is a fixed, bounded formula and rebalancing V1/V2 are deterministic rule-based optimisers. The same inputs always produce the same output (tested). | `ml/agentflow/risk.py`, `rebalance.py`, `rebalance_v2.py`, `tests/test_rebalance_v2.py` |
| No LLM in the decision path | Explanations (English and Bangla) are fixed templates filled with computed numbers. No generative model is called anywhere in the product. | `ml/agentflow/risk.py` |
| Human review | The UI enables **Approve Simulation** only after the reviewer ticks "I have reviewed the evidence above". This is a UI control only; the API itself has no authentication (see B). | `apps/web/src/app/rebalancing/page.tsx` |
| Simulation only | `/api/rebalancing/simulate` returns `simulation_only: true` and does not change the live state (tested). No payment instruction or transfer API exists. | `apps/api/app/service.py`, `tests/test_demo_path.py` |
| Audit trail | Each simulated approval is written to an audit log (newest 200 entries) with recommendation IDs, policy and reviewer note. | `apps/api/app/service.py` |
| Donor safety | Donors stay LOW risk, transfers never exceed the donor's safe surplus, balances never go negative, and the V2 donor reserve is never weaker than V1 (tested). | `tests/test_rebalance.py`, `tests/test_rebalance_v2.py` |
| Anomaly handling | Agents with anomalous activity are held for manual review and get no automatic support. Anomaly is never labelled as fraud (tested). | `tests/test_rebalance.py`, `tests/test_rebalance_v2.py`, `tests/test_demo_path.py` |
| Frontend resilience | API calls time out after 20 s. Failures show a safe error message with Retry and never display stale numbers as live data. | `apps/web/src/lib/api.ts`, `apps/web/src/components/ui.tsx` |
| Reproducible evaluation | A time-based purged split, a feature-leakage test and a fixed seed regenerate every committed metric. V2 parameters were selected on training-period validation folds, never on the test window. | `ml/scripts/run_pipeline.py`, `tests/test_data.py`, `ml/agentflow/policy_selection.py` |

## B. Known prototype limitations

* **No authentication or authorisation.** Anyone who can reach the API can read the synthetic data
  and run simulations. This is acceptable only because no real data or money is involved.
* **No rate limiting** or abuse protection on the public API.
* **In-memory audit log.** It resets when the API restarts, is not tamper-evident and records a free-text
  note, not a verified reviewer identity.
* **Approval acknowledgement is client-side.** The checkbox guards the UI, not the API.
* **No Content-Security-Policy** header yet; the other web headers listed above are set.
* **Models are loaded from local artifacts** built inside the container (joblib). Only trusted,
  self-built artifacts may be loaded.
* **Synthetic data only.** Forecast, risk and impact numbers are not validated on real operations.
* **No dependency or container vulnerability scanning** is configured in CI.

## C. Production hardening path

1. **Identity and access:** SSO/OAuth for operators, role-based access (viewer, reviewer, approver),
   and server-side enforcement of every approval with the reviewer's verified identity.
2. **Separation from money movement:** keep AgentFlow advisory. Any real transfer must go through the
   existing payment/treasury system, with its own maker-checker controls and limits.
3. **Durable, tamper-evident audit:** an append-only store with retention, timestamps and actor
   identity, reviewed regularly.
4. **API protection:** rate limiting, request-size limits, a WAF, TLS everywhere and restrictive CORS
   per environment.
5. **Web hardening:** a strict Content-Security-Policy and HSTS.
6. **Data protection:** use aggregated per-agent amounts and counts only, with no customer-level data.
   Add encryption at rest and in transit, least-privilege data access and a data-retention policy.
7. **Supply chain:** pinned dependencies with automated vulnerability scanning, image scanning and
   signed builds. Model artifacts should be versioned and integrity-checked.
8. **Model governance:** drift and data-quality monitoring, alerting on forecast error and P90 coverage,
   periodic re-validation, and a documented rollback to the previous policy.
9. **Controlled validation:** back-testing on real historical data, then a shadow-mode pilot with
   operations staff before any decision is acted on.

## D. Prompt injection and LLMs

The current core decision path (forecasting, risk scoring, anomaly flagging and rebalancing) uses
**no LLM and no free-form prompt**. Explanations are fixed templates filled with computed values, and
free text such as the reviewer note is stored, not interpreted. **Prompt injection is therefore not a
decision-path attack surface in the current prototype.**

This holds for the current design only, not for every future version. If an LLM is added later
(e.g. an assistant that summarises recommendations), it must be:

* **separated** from consequential financial decision logic: it may describe decisions, never make,
  change or approve them;
* **grounded** in the same computed evidence the deterministic engine produces, with outputs checked
  against those numbers;
* **permissioned**, with no tool access that could trigger transfers, approvals or data changes, and
  with untrusted input (notes, documents) treated as data, not instructions.

## E. Threat examples and mitigations

| Threat | Example | Current mitigation | Production addition |
|---|---|---|---|
| Malformed API input | Oversized lists, unknown fields, wrong types, injection-style strings | Pydantic schemas with `extra="forbid"`, length and range limits, regex IDs, structured 4xx errors without stack traces (tested) | Request-size limits, rate limiting, WAF |
| Unsupported agent / recommendation IDs | `AG-9999`, `not-an-id`, `RB-999`, `DROP TABLE` | Pattern checks return 400; unknown but well-formed IDs return 404 (tested) | Same, plus access control on who may read which agents |
| Manipulated demand data | Inflated transactions to attract cash support | Anomaly detector flags agent-relative surges; anomalous agents are held for manual review, not supported automatically | Source-system integrity checks, reconciliation and investigation workflows |
| Stale or incorrect forecasts | Sudden local spike the model did not foresee | Planning uses a cautious P90 scenario, donors keep a reserve, a person reviews every action, and held-out error and P90 coverage are reported | Drift monitoring, freshness checks on input data, alerting and fallback to the previous policy |
| Unsafe donor selection | Transfer leaves the donor short later | Donor must stay LOW risk, amount ≤ safe surplus, dynamic reserve in V2 (tested). Donor shortages still occur (14 events in 345 simulated V2 transfers), so risk is reduced, not removed | Real-time balance confirmation before execution and donor consent |
| Anomaly misread as fraud | Operator treats an "unusual" badge as proof of wrongdoing | UI and docs state that anomalies are never labelled as fraud; an anomaly only routes the case to manual review (tested) | Formal investigation procedures that are separate from liquidity tooling |
| Unauthorised approval (future production) | Someone approves transfers without authority | Today approvals only simulate and no transfer path exists | Authentication, role-based approvals, maker-checker, server-side limits and a tamper-evident audit |
