# Integration & Scale (Phase 2)

> **Synthetic benchmark evidence — not real upay production performance, and not a real upay integration.**
> Everything below was produced with the project's own synthetic generator on one container.

Judges asked three things: how AgentFlow would connect to a live transaction ledger, whether it can handle
thousands of agents, and how ready it is for integration. This phase answers with a data contract, a
replay proof and a measured benchmark. It adds no new infrastructure (no Kafka, WebSockets or database)
and no new models. Metrics, serving policy, security guardrails and Morning Plan evidence are unchanged.

| Piece | File |
|---|---|
| Feed contract, mapping, replay adapter | `ml/agentflow/integration.py` |
| Evidence script (replay + benchmark) | `ml/scripts/integration_scale.py` |
| Versioned evidence artifact | `ml/artifacts/integration_scale.json` (`phase2-integration-1`) |
| API (read-only) | `GET /api/integration-scale`, `GET /api/integration/feed-schema` |
| UI | Impact & Model Health page → **Integration & Scale — Synthetic Benchmark** |
| Tests | `tests/test_integration_scale.py` (34 tests) |

## 1. Provider-neutral feed contract — `agentflow.feed.v1`

A provider sends **one aggregated record per agent per hour** and keeps a small agent registry. No
individual transactions and no customer data are sent.

**`FeedEvent`** (per agent-hour): `schema_version`, `agent_id`, `hour_start` (Asia/Dhaka local time,
hour-aligned), `closing_cash_bdt`, `closing_efloat_bdt`, `cash_in_count`, `cash_in_amount_bdt`,
`cash_out_count`, `cash_out_requested_bdt`, `cash_out_served_bdt`, `send_money_count`, `payment_count`,
`transaction_count`.

**`AgentRecord`** (registry): `agent_id`, `district`, `location_cluster`, `agent_volume_segment`,
`agent_type`, `outlet_latitude` / `outlet_longitude` (the outlet, never a customer), `market_day`,
`standard_morning_cash_bdt`.

**Strict validation** (Pydantic v2):

* unknown fields are rejected (`extra = forbid`), so an MSISDN or name cannot be added silently;
  field names that look like personal data get a specific error;
* `agent_id` must match `AG-NNNN`;
* `hour_start` must be hour-aligned, with no UTC offset;
* amounts must be finite and ≥ 0;
* counts must be non-negative integers, with no coercion of `"5"` or `5.5`;
* served cash-out must be ≤ requested cash-out;
* `transaction_count` must be ≥ the sum of its components;
* a batch must have no duplicate agent-hours and contain exactly one hour;
* batches must arrive in strictly increasing hour order;
* each agent must be in the registry;
* a batch with any invalid event is rejected whole, so nothing is partially ingested.

**Mapping into AgentFlow's existing inputs** (the columns `features.build_features` reads):

| Feed | AgentFlow column |
|---|---|
| `closing_cash_bdt`, `closing_efloat_bdt` | `cash_balance`, `efloat_balance` |
| `cash_out_requested_bdt`, `cash_out_served_bdt` | `cash_out_amount`, `cash_out_served` |
| requested − served | `unmet_cash_out`; `liquidity_shortage` = unmet > 0 |
| (cash-in + cash-out amount) ÷ cash transactions | `average_transaction_value` |
| counts | same names |
| `hour_start` | `timestamp`, `hour`, `day_of_week`, `is_weekend` (Fri–Sat), `is_salary_period` |
| registry | district, cluster, type, segment, coordinates, `market_day`, `target_cash_level` |

The generator's anomaly labels (`known_anomaly_label`, `anomaly_type`) are evaluation ground truth only.
They are not part of a feed, and the decision path never reads them. A test shows that the round trip
(synthetic rows → JSON events → AgentFlow columns) reproduces the stored inputs exactly. The JSON Schema
is served at `GET /api/integration/feed-schema`.

## 2. Deterministic replay adapter and equivalence proof

`ReplayFeed` emits the stored synthetic dataset as hourly batches in chronological order. The order is
fixed even if the input rows are shuffled.

`StreamingDecisionAdapter` validates and ingests each batch and keeps only a bounded rolling window of
216 hours: 168-hour rolling statistics plus 7-day same-hour lags need 171 hours. It also keeps running
per-agent shortage counts for the training period. On request it builds the decision snapshot with the
**unchanged** feature code, forecast models, anomaly detector and risk formula.

**Result** (from `integration_scale.json`):

* Replay ran from the first hour (2026-06-17 00:00) to 2026-08-31 13:00: 1,814 hours and 362,800 events,
  all validated, 0 rejected.
* At four held-out timestamps the replayed snapshot matches the existing batch pipeline
  (`Engine.load(serving=True)`, as used by the API) for every one of the 200 agents:
  * the timestamps are 2026-08-18 09:00, 2026-08-22 17:00, 2026-08-27 03:00 and 2026-08-31 13:00
    (the default demo time);
  * risk level, anomaly status and review priority are identical;
  * the maximum numeric difference is 0.0, within a tolerance of 1e-6.
* The streamed historical shortage rate equals the batch training statistic.
* Decision digests (every agent's risk level, anomaly status and review priority) are stored and re-checked by
  the tests, which proves determinism across runs. Numeric fields are compared with a tolerance instead,
  because models retrained on another CPU (for example in CI) differ in the last float bits.
* A replay that starts only 216 hours before the decision, with the training statistic supplied, gives
  the same decision. This shows that the window is sufficient.

## 3. Decision-path scale benchmark

The benchmark uses the same synthetic generator with a fixed seed (20260907): N agents × 9 days, which is
the rolling window. Each scale runs in its own process. One **hourly refresh** has these steps:

1. Validate the newest hour's events.
2. Rebuild features over the window.
3. Run the trained forecast and anomaly models (existing `Engine`).
4. Assemble the snapshot (risk and anomaly).
5. Build the V1 and serving-V2 peer-transfer plans.

Timings are the median of 3 runs; data generation is excluded. Peak memory is the worker's peak resident
set size (`VmHWM`), including Python, libraries and models (about 235 MB before any data).

Environment: Intel Xeon @ 2.10 GHz, 4 logical CPUs, 15.7 GB RAM, Python 3.11, single process, no
parallelism added.

| Synthetic agents | Rows in window | Hourly refresh | Features | Model inference (window) | V2 plan | Contract validation | Peak memory |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 200 | 43,200 | 0.61 s | 0.16 s | 0.32 s | 0.03 s | ~17,700 events/s | 295 MB |
| 1,000 | 216,000 | 2.30 s | 0.57 s | 1.42 s | 0.10 s | ~35,100 events/s | 437 MB |
| 5,000 | 1,080,000 | 12.0 s | 3.26 s | 6.46 s | 0.94 s | ~40,200 events/s | 1.1 GB |
| 10,000 | 2,160,000 | 23.6 s | 7.12 s | 12.1 s | 1.79 s | ~27,500 events/s | 1.9 GB |

10,000 agents was practical on this container without changing any implementation, so it is included.
Across our runs of the script, total refresh times differed by up to about 12% and small individual stages by up to about 20%:
treat them as orders of magnitude, not service levels.

### Bottlenecks (reported honestly)

* **Full-window recomputation.** At 10,000 agents, forecast and anomaly inference over the whole window
  takes about 51% of the refresh and the feature rebuild about 30%. The existing engine recomputes all
  216 hours on every refresh, although only the newest hour changes. Model inference for the decision
  hour alone measured about 0.49 s at 10,000 agents. Caching earlier hours' features and scores would
  avoid most of the recomputation; it is **not implemented or measured** (no redesign in this phase).
* **Peer-transfer search.** V2 is a Python loop over recipients × same-district donors. It grew 43× and
  54× for 50× more agents in two runs, so it is close to or slightly faster than linear. It is still a
  small share of the refresh, but it is the stage most likely to grow faster than linearly when many
  agents are at risk at once.
* **Memory.** Peak memory grows by about 170 MB per extra 1,000 agents; the whole rolling window is held in
  memory as pandas frames.
* **Contract validation is not a bottleneck.** It costs about 0.36 s per hourly batch at 10,000 agents.
  Validation throughput was lower at 10,000 agents than at 5,000 in this run; we did not investigate why.

## 4. Limitations

* Synthetic data and one container; no network, queue or database in the measured path.
* The replay is a deterministic file replay through the contract. It is not a live ledger connection,
  streaming broker or real upay integration.
* There is no authentication on the feed. Real ingestion would also need transport security, provider
  authentication, late or missing-hour handling and back-pressure, none of which is implemented.
* Timings depend on hardware and load. They are not production performance or a service-level guarantee.

Reproduce: `python ml/scripts/integration_scale.py` (about 3 minutes; optional `--scales 200,1000 --repeats 3`).
