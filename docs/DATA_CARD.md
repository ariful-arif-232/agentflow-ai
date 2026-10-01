# Data Card — AgentFlow Synthetic MFS Agent Dataset

> **Synthetic data for hackathon prototyping — not production upay data.**
> No real customer, agent, transaction or location record was used to create it.

## Purpose

Provide a realistic, *learnable* and fully reproducible stand-in for hourly MFS agent
activity so that AgentFlow's forecasting, anomaly detection, risk scoring, rebalancing
and impact simulation can be built, evaluated and demonstrated end-to-end without any
access to production data.

## How to regenerate

```bash
python ml/scripts/generate_data.py      # writes ml/data/*.parquet + ml/artifacts/dataset_summary.json
```

Generation is deterministic (`numpy.random.default_rng(seed=2026)`); the same seed
always yields byte-identical data (enforced by `tests/test_data.py`).

## Size and coverage

| Item | Value |
|---|---|
| Agents | 200 (synthetic IDs `AG-0001` … `AG-0200`) |
| Time coverage | 2026-06-17 00:00 → 2026-08-31 23:00 (76 days) |
| Granularity | hourly |
| Rows | 364,800 agent-hours |
| Districts | Dhaka 50, Chattogram 35, Gazipur 25, Sylhet 20, Rajshahi 20, Khulna 20, Rangpur 15, Barishal 15 |
| Location clusters | urban_core 68, urban_periphery 57, rural 75 |
| Volume segments | low 64, medium 98, high 38 |
| Held-out test period | 2026-08-18 → 2026-08-31 (last 14 days, ~18%) |

## Files

* `ml/data/agents.parquet` — one row per agent (static attributes).
* `ml/data/agent_hourly.parquet` — one row per agent-hour.

### Agent attributes

| Field | Meaning |
|---|---|
| `agent_id` | synthetic identifier |
| `district`, `location_cluster` | operational location grouping (urban_core / urban_periphery / rural) |
| `agent_type` | retail_shop, grocery, pharmacy, market_stall, transport_hub |
| `agent_volume_segment` | low / medium / high expected volume |
| `synthetic_latitude`, `synthetic_longitude` | random point around a district centroid (cluster-dependent radius) — **not a real shop location** |
| `base_daily_cash_out`, `cash_in_ratio` | latent generator parameters (not used as model features) |
| `market_day` | weekly "haat" day for rural agents (-1 otherwise) |
| `target_cash_level` | static morning cash level under the status-quo manual policy |

### Hourly fields

`timestamp, cash_balance, efloat_balance, cash_in_count, cash_in_amount, cash_out_count,
cash_out_amount, cash_out_served, unmet_cash_out, send_money_count, payment_count,
transaction_count, average_transaction_value, hour, day_of_week, is_weekend,
is_salary_period, liquidity_shortage, known_anomaly_label, anomaly_type`

* `cash_out_amount` is **requested** cash-out demand (served + declined). We assume
  declined cash-out attempts are logged, which is what makes unmet demand measurable.
* `cash_balance` is the agent's cash at the *end* of the hour.
* `liquidity_shortage = 1` when some requested cash-out could not be served in that hour.

Derived lag / rolling / target columns (`lag_1h`, `lag_6h`, `lag_24h`, `rolling_mean_6h`,
`rolling_mean_24h`, `rolling_std_24h`, `transaction_velocity`, `future_6h_cash_demand`,
`future_6h_net_cash_demand`, …) are computed by `ml/agentflow/features.py` so they can never
drift from the raw data.

## Generation assumptions (injected patterns)

| Pattern | Implementation |
|---|---|
| Hour-of-day profile | Two daily peaks per flow; cluster-specific timing and opening hours (rural closes earlier) |
| Weekday / weekend | Bangladesh weekend (Fri, Sat) dip; Thursday pre-weekend uplift |
| Salary period | Days 27–3 (shoulders 25–26, 4–5): cash-out +30% urban core, **+62% urban periphery** (garment-worker style), +28% rural; cash-in uplift ~⅓ of that |
| Market day | Each rural agent has one weekly haat day with ×1.45 demand |
| Agent baselines | Segment base volume × agent-level log-normal factor; cluster-dependent cash-in/out mix (urban core is cash-in heavy → natural surplus donors) |
| Day regimes | AR(1) day-level log shock per agent (φ = 0.6, σ = 0.10) |
| Legitimate spikes | ~1 per agent per 10 days, ×1.6–2.6 cash-out for 2–5 hours |
| Noise | Multiplicative log-normal hourly noise (σ = 0.33) |
| Status-quo cash policy | Drawer reset to a static `target_cash_level` (42–85% of expected daily cash-out) at 08:00 daily; it ignores salary periods, market days and spikes |

## Injected behavioural anomalies (ground truth for evaluation)

426 episodes (944 labelled agent-hours, ~0.26%), `known_anomaly_label = 1` with `anomaly_type`:

| Type | Behaviour |
|---|---|
| `rapid_burst` | transaction count ×4–6.5 with cash-out ×1.6–2.4 for 2–4 h |
| `large_ticket` | cash-out ×2.6–3.8 with fewer, larger transactions for 1–2 h |
| `odd_hour` | 6–12% of daily volume transacted between 01:00 and 04:00 |
| `cash_churn` | cash-in **and** cash-out ×2.6–3.6 simultaneously (round-tripping-like) |

Six of these episodes are deliberately scheduled in the final 30 hours so the
dashboard's demo window contains labelled anomalies. Anomalies are *behavioural*
patterns for testing an unsupervised detector; they are **not** labels of fraud.

## Privacy statement

* No personally identifiable information is generated: no names, phone numbers,
  national IDs, account numbers or customer records (asserted by `tests/test_data.py`).
* Coordinates are random points around public district centroids.
* The dataset is safe to publish in a public repository.

## Limitations

* Patterns are hand-designed; real agent behaviour will contain effects not modelled
  here (Eid / festival seasonality, weather, network outages, inter-agent substitution,
  distributor logistics constraints, e-float limits).
* Customer demand is exogenous: shortages do not cause customers to retry later or move
  to a neighbouring agent.
* E-float is tracked but not used as a binding constraint.
* Distances are straight-line (haversine), not road travel time.

## Future real-data validation

1. Replace the generator with an extract of hourly agent ledger aggregates (no customer PII
   required — only per-agent amounts and counts).
2. Re-run `train.py` / `evaluate.py` unchanged; the time-based split and leakage tests apply as-is.
3. Validate that declined cash-out attempts are logged; otherwise unmet demand must be
   estimated (censored-demand problem).
4. Back-test the impact simulator against historical rebalancing logs before any pilot.
