"""Phase-2 integration & scale evidence: feed contract, replay equivalence and a decision-path benchmark.

Synthetic benchmark evidence — not real upay production performance and not a real upay integration.

Usage:  python ml/scripts/integration_scale.py [--scales 200,1000,5000,10000] [--repeats 3]

Writes ml/artifacts/integration_scale.json. Kept separate from run_pipeline.py because wall-clock timings
vary from run to run; the deterministic parts (replay equivalence, decision counts, snapshot digests) are
re-checked by tests/test_integration_scale.py.

1. Replay: the stored synthetic dataset is replayed hour by hour, in chronological order, through the
   agentflow.feed.v1 contract (every event validated) into StreamingDecisionAdapter. At selected held-out
   timestamps its decision snapshot is compared with the existing batch pipeline (Engine.load(serving=True)).
2. Benchmark: for each scale, a fresh synthetic population (same generator, fixed seed) of N agents × 9 days
   is pushed through the existing decision path, in a separate process so the peak resident memory of that
   scale can be read. Stages are timed with time.perf_counter; the median of the repeats is reported.
"""
from __future__ import annotations

import _bootstrap  # noqa: F401

import argparse
import hashlib
import json
import os
import platform
import resource
import statistics
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from agentflow import anomaly, config, data_gen, engine, features, forecast, integration, rebalance, rebalance_v2

VERSION = "phase2-integration-1"
OUT = config.ARTIFACTS_DIR / "integration_scale.json"
REPLAY_TARGETS = ("2026-08-18 09:00", "2026-08-22 17:00", "2026-08-27 03:00", "2026-08-31 13:00")
DEFAULT_SCALES = (200, 1000, 5000, 10000)
BENCH_SEED = 20260907
BENCH_DAYS = engine.SERVING_HISTORY_DAYS  # the rolling window the decision path needs
BENCH_START = config.TEST_START - pd.Timedelta(days=BENCH_DAYS)
BENCH_DECISION = BENCH_START + pd.Timedelta(days=BENCH_DAYS - 1, hours=13)  # last day, 13:00 (busy hour)
STAGES = ("contract_validate_hour", "feature_build_window", "engine_inference_window", "snapshot_risk_anomaly",
          "plan_v1", "plan_v2_serving")


def snapshot_digest(snap: pd.DataFrame) -> str:
    cols = ["agent_id", *integration.SNAPSHOT_EXACT_COLUMNS, *integration.SNAPSHOT_COMPARE_COLUMNS]
    s = snap[cols].sort_values("agent_id").copy()
    for c in integration.SNAPSHOT_COMPARE_COLUMNS:
        s[c] = s[c].astype(float).round(6)
    return hashlib.sha256(s.to_csv(index=False).encode()).hexdigest()


def rss_mb() -> float:
    """Peak resident set size of this process (VmHWM). ru_maxrss is only a fallback: on Linux it keeps the
    parent's high-water mark across fork/exec, which would overstate a small worker's memory."""
    status = Path("/proc/self/status")
    if status.exists():
        for line in status.read_text().splitlines():
            if line.startswith("VmHWM:"):
                return round(int(line.split()[1]) / 1024, 1)
    return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1)


# ------------------------------------------------------------------ replay equivalence
def run_replay() -> dict:
    data = data_gen.load()
    bundle, det = forecast.ForecastBundle.load(), anomaly.AnomalyDetector.load()
    ref = engine.Engine.load(serving=True)
    targets = [pd.Timestamp(t) for t in REPLAY_TARGETS]
    adapter = integration.StreamingDecisionAdapter(integration.agents_to_records(data.agents), bundle, det)
    results, ingest_s, t0 = [], 0.0, time.perf_counter()
    for ts, batch in integration.ReplayFeed(data.hourly, end=max(targets)):
        t = time.perf_counter()
        adapter.ingest(batch)
        ingest_s += time.perf_counter() - t
        if ts in targets:
            t = time.perf_counter()
            snap = adapter.snapshot()
            snap_s = time.perf_counter() - t
            cmp = integration.compare_snapshots(snap, ref.snapshot(ts))
            results.append({
                "timestamp": str(ts), **cmp, "replay_snapshot_digest": snapshot_digest(snap),
                "batch_snapshot_digest": snapshot_digest(ref.snapshot(ts)),
                "high_or_critical_agents": int(snap["risk_level"].isin(["HIGH", "CRITICAL"]).sum()),
                "non_normal_anomaly_agents": int((snap["anomaly_status"] != "NORMAL").sum()),
                "snapshot_seconds": round(snap_s, 3),
            })
    hist_ok = bool((adapter.hist_rate().sort_index() - engine.training_shortage_rate(data.hourly).sort_index()).abs().max() < 1e-12)
    return {
        "source": "stored synthetic dataset (ml/data), replayed from its first hour",
        "first_hour": str(data.hourly["timestamp"].min()), "last_hour_replayed": str(adapter.last_hour),
        "hours_replayed": int(data.hourly.loc[data.hourly["timestamp"] <= max(targets), "timestamp"].nunique()),
        "events_validated": adapter.events_ingested, "events_rejected": 0,
        "agents": int(data.agents.shape[0]), "window_hours": adapter.window_hours,
        "ingest_seconds_total": round(ingest_s, 2), "wall_seconds_total": round(time.perf_counter() - t0, 1),
        "hist_shortage_rate_matches_batch": hist_ok,
        "reference": "Engine.load(serving=True).snapshot(ts) — the existing batch pipeline used by the API",
        "comparison": "numeric decision fields within rtol = atol = 1e-6; risk level, anomaly status and review "
                      "priority must be identical for every agent",
        "targets": results, "all_match": all(r["match"] for r in results),
    }


# ------------------------------------------------------------------ benchmark (one scale per process)
def worker(n: int, repeats: int) -> dict:
    bundle, det = forecast.ForecastBundle.load(), anomaly.AnomalyDetector.load()
    rss_models = rss_mb()
    t = time.perf_counter()
    g = data_gen.generate(seed=BENCH_SEED, n_agents=n, n_days=BENCH_DAYS, start=BENCH_START)
    gen_s = time.perf_counter() - t
    t = time.perf_counter()
    [integration.AgentRecord.model_validate(r) for r in integration.agents_to_records(g.agents)]
    registry_s = time.perf_counter() - t
    hour_rows = g.hourly[g.hourly["timestamp"] == BENCH_DECISION]
    payloads = integration.hourly_to_events(hour_rows)
    hist = engine.training_shortage_rate(g.hourly)  # shortage rate over the benchmark window's operating hours
    times = {s: [] for s in STAGES}
    times["decision_hour_model_inference"] = []
    for _ in range(repeats):
        t = time.perf_counter(); integration.to_hourly_frame(integration.validate_batch(payloads)); times["contract_validate_hour"].append(time.perf_counter() - t)
        t = time.perf_counter(); f = features.build_features(g.hourly, g.agents); times["feature_build_window"].append(time.perf_counter() - t)
        t = time.perf_counter(); e = engine.Engine(agents=g.agents, feats=f, bundle=bundle, detector=det, hist_rate=hist); times["engine_inference_window"].append(time.perf_counter() - t)
        t = time.perf_counter(); snap = e.snapshot(BENCH_DECISION); times["snapshot_risk_anomaly"].append(time.perf_counter() - t)
        t = time.perf_counter(); p1 = rebalance.recommend(snap); times["plan_v1"].append(time.perf_counter() - t)
        t = time.perf_counter(); p2 = rebalance_v2.recommend_v2(snap, rebalance_v2.selected_config()); times["plan_v2_serving"].append(time.perf_counter() - t)
        rows = f[f["timestamp"] == BENCH_DECISION]
        t = time.perf_counter(); bundle.predict(rows); det.score(anomaly.anomaly_features(rows)); times["decision_hour_model_inference"].append(time.perf_counter() - t)
        del e, f
    med = {k: round(statistics.median(v), 4) for k, v in times.items()}
    refresh = round(sum(med[s] for s in STAGES), 4)
    return {
        "agents": n, "window_hours": BENCH_DAYS * 24, "rows_in_window": int(len(g.hourly)), "repeats": repeats,
        "decision_time": str(BENCH_DECISION),
        "median_seconds": med, "min_seconds": {k: round(min(v), 4) for k, v in times.items()},
        "max_seconds": {k: round(max(v), 4) for k, v in times.items()},
        "hourly_refresh_seconds": refresh,
        "agents_per_second_refresh": round(n / refresh, 1),
        "events_per_second_validation": round(n / med["contract_validate_hour"], 0),
        "registry_validation_seconds": round(registry_s, 4), "data_generation_seconds_excluded": round(gen_s, 2),
        "peak_rss_mb": rss_mb(), "rss_after_model_load_mb": rss_models,
        "decisions": {
            "risk_levels": {k: int(v) for k, v in snap["risk_level"].value_counts().sort_index().items()},
            "anomaly_statuses": {k: int(v) for k, v in snap["anomaly_status"].value_counts().sort_index().items()},
            "v1_transfers": len(p1["recommendations"]), "v2_transfers": len(p2["recommendations"]),
            "v2_held_for_review": len(p2["held_for_review"]), "snapshot_digest": snapshot_digest(snap),
        },
    }


def run_benchmark(scales, repeats: int) -> list[dict]:
    out = []
    for n in scales:
        print(f"  benchmark {n} agents …", flush=True)
        r = subprocess.run([sys.executable, __file__, "--worker", str(n), "--repeats", str(repeats)],
                           capture_output=True, text=True, check=True)
        out.append(json.loads(r.stdout.strip().splitlines()[-1]))
        print(f"    refresh {out[-1]['hourly_refresh_seconds']} s · peak RSS {out[-1]['peak_rss_mb']} MB", flush=True)
    return out


def environment() -> dict:
    import numpy, sklearn  # noqa: E401
    cpu = next((ln.split(":", 1)[1].strip() for ln in Path("/proc/cpuinfo").read_text().splitlines()
                if ln.startswith("model name")), platform.processor()) if Path("/proc/cpuinfo").exists() else platform.processor()
    mem = None
    if Path("/proc/meminfo").exists():
        kb = int(Path("/proc/meminfo").read_text().split("MemTotal:")[1].split()[0])
        mem = round(kb / 1024 / 1024, 1)
    return {"python": platform.python_version(), "platform": platform.platform(), "cpu_model": cpu,
            "logical_cpus": os.cpu_count(), "memory_gb": mem, "numpy": numpy.__version__, "pandas": pd.__version__,
            "scikit_learn": sklearn.__version__, "process": "single Python process per scale, no parallelism added"}


def bottlenecks(bench: list[dict]) -> list[str]:
    big = bench[-1]
    m = big["median_seconds"]
    share = {s: m[s] / big["hourly_refresh_seconds"] for s in STAGES}
    top = sorted(share, key=share.get, reverse=True)[:2]
    names = {"engine_inference_window": "forecast + anomaly inference over the whole rolling window",
             "feature_build_window": "feature rebuild over the whole 216-hour window",
             "plan_v2_serving": "V2 peer-transfer search (Python loop over recipients × same-district donors)",
             "plan_v1": "V1 peer-transfer search (Python loop)", "snapshot_risk_anomaly": "snapshot assembly",
             "contract_validate_hour": "per-event contract validation"}
    small, n0, n1 = bench[0], bench[0]["agents"], big["agents"]
    growth = big["hourly_refresh_seconds"] / small["hourly_refresh_seconds"]
    v2_growth = big["median_seconds"]["plan_v2_serving"] / max(small["median_seconds"]["plan_v2_serving"], 1e-9)
    shape = "faster than the agent count" if v2_growth > n1 / n0 else "roughly in line with the agent count"
    mid = next((b for b in bench if b["agents"] * 2 == n1), None)
    mem = (f"about {(big['peak_rss_mb'] - mid['peak_rss_mb']) / ((n1 - mid['agents']) / 1000):,.0f} MB per extra 1,000 agents "
           f"between {mid['agents']:,} and {n1:,}") if mid else "with the number of rows in the window"
    return [
        f"At {n1:,} agents the two largest stages are {names[top[0]]} ({share[top[0]]:.0%}) and {names[top[1]]} "
        f"({share[top[1]]:.0%}) of the measured hourly refresh.",
        f"The existing engine recomputes features, forecasts and anomaly scores for the full {big['window_hours']}-hour "
        "window on every refresh, although only the newest hour changes. Model inference for the decision hour alone "
        f"measured {m['decision_hour_model_inference']:.3f} s at {n1:,} agents. Caching earlier hours' features and scores "
        "would avoid most of that recomputation; it is not implemented or measured here (no redesign in this phase).",
        f"Refresh time grew {growth:.0f}× from {n0:,} to {n1:,} agents ({n1 / n0:.0f}× more agents). The V2 transfer "
        f"search grew {v2_growth:.0f}×, {shape} at these scales; its candidate pairs are recipients × same-district donors, "
        "so it can grow faster than linearly if more agents are at risk at once.",
        f"Peak resident memory grew {mem}, reaching {big['peak_rss_mb']:,.0f} MB at {n1:,} agents including Python, "
        f"libraries and models (~{bench[0]['rss_after_model_load_mb']:.0f} MB before any data). The whole rolling window "
        "is held in memory as pandas frames.",
    ]


def contract_section() -> dict:
    schema = integration.json_schema()
    return {
        "schema_version": integration.SCHEMA_VERSION,
        "schema_sha256": hashlib.sha256(json.dumps(schema, sort_keys=True).encode()).hexdigest(),
        "granularity": "one aggregated record per agent per hour; no individual transactions",
        "personal_data": "none — no customer, owner, phone, national-ID or account fields; unknown fields are rejected "
                         "and field names that look like personal data are refused",
        "feed_event_fields": list(integration.FeedEvent.model_fields),
        "agent_record_fields": list(integration.AgentRecord.model_fields),
        "mapping": [
            {"feed": "closing_cash_bdt", "agentflow": "cash_balance"},
            {"feed": "closing_efloat_bdt", "agentflow": "efloat_balance"},
            {"feed": "cash_in_count / cash_in_amount_bdt", "agentflow": "cash_in_count / cash_in_amount"},
            {"feed": "cash_out_count / cash_out_requested_bdt", "agentflow": "cash_out_count / cash_out_amount"},
            {"feed": "cash_out_served_bdt", "agentflow": "cash_out_served"},
            {"feed": "requested − served", "agentflow": "unmet_cash_out, liquidity_shortage (unmet > 0)"},
            {"feed": "(cash-in + cash-out amount) ÷ cash transactions", "agentflow": "average_transaction_value"},
            {"feed": "send_money_count / payment_count / transaction_count", "agentflow": "same names"},
            {"feed": "hour_start (Asia/Dhaka, hour-aligned)", "agentflow": "timestamp, hour, day_of_week, is_weekend (Fri–Sat), is_salary_period"},
            {"feed": "AgentRecord registry", "agentflow": "district, location_cluster, agent_type, volume segment, outlet coordinates, market_day, target_cash_level"},
        ],
        "validation_rules": [
            "schema_version must be agentflow.feed.v1", "unknown fields rejected (extra = forbid)",
            "personal-data-like field names rejected", "agent_id pattern AG-NNNN", "hour_start hour-aligned, no UTC offset",
            "amounts finite and ≥ 0", "counts are non-negative integers (no coercion)",
            "cash_out_served ≤ cash_out_requested", "transaction_count ≥ sum of component counts",
            "no duplicate agent-hour in a batch", "one hour per batch, strictly increasing", "agent must be in the registry",
        ],
        "not_in_feed": "known_anomaly_label and anomaly_type exist only in the synthetic generator (evaluation ground truth)",
    }


def main(scales, repeats: int) -> dict:
    t0 = time.perf_counter()
    print("  replay equivalence …", flush=True)
    replay = run_replay()
    print(f"    all targets match: {replay['all_match']}", flush=True)
    bench = run_benchmark(scales, repeats)
    out = {
        "version": VERSION,
        "label": integration.LABEL,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "command": "python ml/scripts/integration_scale.py",
        "contract": contract_section(),
        "replay": replay,
        "benchmark": {
            "label": "Synthetic benchmark evidence — not real upay production performance.",
            "method": "Same synthetic generator, fixed seed, N agents × 9 days (the decision path's rolling window). "
                      "One hourly refresh = validate the newest hour's events, rebuild features over the window, run "
                      "the trained forecast and anomaly models (existing Engine), assemble the decision snapshot, then "
                      "build the V1 and serving V2 peer-transfer plans. Median of repeats; data generation excluded. "
                      "Peak memory is the worker process's peak resident set size (VmHWM from /proc/self/status).",
            "seed": BENCH_SEED, "decision_time": str(BENCH_DECISION), "stages": list(STAGES),
            "scales_requested": list(scales), "scales": bench,
            "bottlenecks": bottlenecks(bench),
        },
        "environment": environment(),
        "limitations": [
            "Synthetic data and a single container; no network, queue or database in the measured path.",
            "Replay is a deterministic file replay through the contract, not a live ledger connection or streaming broker.",
            "Timings vary with hardware and load; treat them as orders of magnitude, not service-level guarantees.",
            "Not real upay production performance, and not evidence of a real upay integration.",
        ],
        "total_seconds": round(time.perf_counter() - t0, 1),
    }
    OUT.write_text(json.dumps(out, indent=2) + "\n")
    print(f"  wrote {OUT}")
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--worker", type=int)
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--scales", default=",".join(map(str, DEFAULT_SCALES)))
    a = ap.parse_args()
    if a.worker:
        print(json.dumps(worker(a.worker, a.repeats)))
    else:
        main(tuple(int(x) for x in a.scales.split(",")), a.repeats)
