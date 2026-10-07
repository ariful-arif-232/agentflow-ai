"""Phase-2 integration & scale: feed-contract validation, replay equivalence/determinism, benchmark artifact integrity.

Synthetic benchmark evidence — not real upay production performance and not a real upay integration.
"""
import json
import math
import subprocess
import sys
import warnings
from datetime import datetime
from pathlib import Path

import pandas as pd
import pytest

from agentflow import anomaly, config, data_gen, engine, forecast, integration as I

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = config.ARTIFACTS_DIR / "integration_scale.json"
TARGETS = (pd.Timestamp("2026-08-18 09:00"), pd.Timestamp("2026-08-31 13:00"))


def _event(**over):
    e = {"schema_version": "agentflow.feed.v1", "agent_id": "AG-0171", "hour_start": "2026-08-31T13:00:00",
         "closing_cash_bdt": 12000.0, "closing_efloat_bdt": 30000.0, "cash_in_count": 3, "cash_in_amount_bdt": 4500.0,
         "cash_out_count": 5, "cash_out_requested_bdt": 9000.0, "cash_out_served_bdt": 8000.0, "send_money_count": 2,
         "payment_count": 1, "transaction_count": 11}
    e.update(over)
    return e


@pytest.fixture(scope="module")
def data():
    return data_gen.load()


@pytest.fixture(scope="module")
def artifact():
    return json.loads(ARTIFACT.read_text())


# ------------------------------------------------------------------ contract validation
def test_valid_event_maps_to_agentflow_columns():
    ev = I.validate_batch([_event()])
    row = I.to_hourly_frame(ev).iloc[0]
    assert row["cash_out_amount"] == 9000.0 and row["cash_out_served"] == 8000.0 and row["unmet_cash_out"] == 1000.0
    assert row["liquidity_shortage"] == 1 and row["average_transaction_value"] == round(13500 / 8, 2)
    assert (row["hour"], row["day_of_week"], bool(row["is_weekend"]), bool(row["is_salary_period"])) == (13, 0, False, True)
    assert "known_anomaly_label" not in I.to_hourly_frame(ev).columns  # evaluation labels are never part of a feed


@pytest.mark.parametrize("over, why", [
    ({"customer_msisdn": "01700000000"}, "personal data"),
    ({"owner_name": "x"}, "personal data"),
    ({"notes": "x"}, "Extra inputs"),
    ({"schema_version": "agentflow.feed.v0"}, "agentflow.feed.v1"),
    ({"agent_id": "171"}, "pattern"),
    ({"hour_start": "2026-08-31T13:30:00"}, "aligned"),
    ({"hour_start": "2026-08-31T13:00:00+06:00"}, "UTC offset"),
    ({"closing_cash_bdt": -1.0}, "greater than or equal"),
    ({"cash_in_amount_bdt": float("nan")}, "finite"),
    ({"cash_out_requested_bdt": float("inf")}, "finite"),
    ({"cash_out_count": "5"}, "integer"),
    ({"cash_out_count": 5.5}, "integer"),
    ({"cash_out_served_bdt": 9500.0}, "cannot exceed"),
    ({"transaction_count": 10}, "at least the sum"),
])
def test_malformed_events_are_rejected(over, why):
    with pytest.raises(ValueError) as exc:
        I.validate_batch([_event(**over)])
    assert why.lower() in str(exc.value).lower()


def test_batch_rejects_duplicates_atomically():
    with pytest.raises(ValueError, match="duplicate agent-hour"):
        I.validate_batch([_event(), _event()])
    with pytest.raises(ValueError, match="2 invalid"):  # every bad event is reported; nothing is partially ingested
        I.validate_batch([_event(closing_cash_bdt=-1), _event(agent_id="AG-0001"), _event(agent_id="AG-0002", foo=1)])


def test_agent_registry_is_validated():
    ok = {"agent_id": "AG-0001", "district": "Dhaka", "location_cluster": "urban_core", "agent_volume_segment": "high",
          "agent_type": "retail_shop", "outlet_latitude": 23.8, "outlet_longitude": 90.4, "market_day": -1,
          "standard_morning_cash_bdt": 50000.0}
    I.AgentRecord.model_validate(ok)
    for bad in ({"outlet_latitude": 51.5}, {"location_cluster": "suburb"}, {"phone": "x"}, {"market_day": 7}):
        with pytest.raises(ValueError):
            I.AgentRecord.model_validate({**ok, **bad})


def test_json_schema_is_strict_and_free_of_personal_data():
    s = I.json_schema()
    assert s["schema_version"] == I.SCHEMA_VERSION == "agentflow.feed.v1"
    for part in ("feed_event", "agent_record"):
        assert s[part]["additionalProperties"] is False
        assert not [k for k in s[part]["properties"] if I.PII_PATTERN.search(k)]


def test_mapping_reproduces_the_stored_hourly_inputs_exactly(data):
    """Contract round trip: synthetic rows → feed events → AgentFlow columns equals the original columns."""
    rows = data.hourly[data.hourly["timestamp"].between(pd.Timestamp("2026-08-30 00:00"), pd.Timestamp("2026-08-30 23:00"))]
    events = json.loads(json.dumps(I.hourly_to_events(rows), default=str))  # through JSON, as a provider would send it
    back = I.to_hourly_frame(I.validate_batch(events)).sort_values(["agent_id", "timestamp"]).reset_index(drop=True)
    orig = rows.sort_values(["agent_id", "timestamp"]).reset_index(drop=True)
    for c in [*I.FEED_COLUMNS, "average_transaction_value", "hour", "day_of_week", "is_weekend", "is_salary_period",
              "liquidity_shortage", "timestamp", "agent_id"]:
        pd.testing.assert_series_equal(back[c], orig[c], check_dtype=False, check_names=False, obj=c)


# ------------------------------------------------------------------ adapter rules
@pytest.fixture(scope="module")
def models():
    return forecast.ForecastBundle.load(), anomaly.AnomalyDetector.load()


def test_adapter_rejects_out_of_order_mixed_and_unknown(data, models):
    ad = I.StreamingDecisionAdapter(I.agents_to_records(data.agents), *models)
    feed = iter(I.ReplayFeed(data.hourly, start=pd.Timestamp("2026-08-30 00:00")))
    (t0, b0), (t1, b1) = next(feed), next(feed)
    ad.ingest(b1)
    with pytest.raises(ValueError, match="out-of-order"):
        ad.ingest(b0)
    with pytest.raises(ValueError, match="exactly one hour"):
        ad.ingest(b0[:1] + next(feed)[1][1:2])
    with pytest.raises(ValueError, match="missing from the registry"):
        ad.ingest([_event(agent_id="AG-9999", hour_start=datetime(2026, 8, 31, 0))])
    assert ad.last_hour == t1 and ad.events_ingested == len(b1)  # rejected batches changed nothing


def test_replay_is_chronological_and_deterministic(data):
    a = I.ReplayFeed(data.hourly, start=pd.Timestamp("2026-08-30 20:00"), end=pd.Timestamp("2026-08-31 02:00"))
    b = I.ReplayFeed(data.hourly.sample(frac=1.0, random_state=7), start=pd.Timestamp("2026-08-30 20:00"),
                     end=pd.Timestamp("2026-08-31 02:00"))  # input order does not matter
    la, lb = list(a), list(b)
    assert [t for t, _ in la] == sorted(t for t, _ in la) and len(la) == 7
    assert la == lb and all(len(batch) == 200 for _, batch in la)


# ------------------------------------------------------------------ replay equivalence (full replay from the first hour)
@pytest.fixture(scope="module")
def replay(data, models):
    ad = I.StreamingDecisionAdapter(I.agents_to_records(data.agents), *models)
    snaps = {}
    for ts, batch in I.ReplayFeed(data.hourly, end=max(TARGETS)):
        ad.ingest(batch)
        if ts in TARGETS:
            snaps[ts] = ad.snapshot()
        assert len(ad._window) <= I.WINDOW_HOURS  # bounded memory: only the rolling window is kept
    return ad, snaps


@pytest.fixture(scope="module")
def batch_engine():
    return engine.Engine.load(serving=True)


@pytest.mark.parametrize("ts", TARGETS)
def test_replay_snapshot_matches_existing_pipeline(replay, batch_engine, ts):
    res = I.compare_snapshots(replay[1][ts], batch_engine.snapshot(ts))
    assert res["match"] and res["agents"] == 200 and all(res["categorical_identical"].values())
    assert res["max_abs_numeric_diff"] <= 1e-6


def test_streaming_hist_rate_equals_training_statistic(replay, data):
    a = replay[0].hist_rate().sort_index()
    b = engine.training_shortage_rate(data.hourly).sort_index()
    assert list(a.index) == list(b.index) and (a - b).abs().max() < 1e-12


def test_replay_snapshots_are_reproducible_across_runs(replay, artifact):
    sys.path.insert(0, str(ROOT / "ml" / "scripts"))
    import integration_scale
    recorded = {t["timestamp"]: t["replay_snapshot_digest"] for t in artifact["replay"]["targets"]}
    for ts, snap in replay[1].items():
        assert integration_scale.snapshot_digest(snap) == recorded[str(ts)]


def test_a_window_only_replay_gives_the_same_decision(data, models, replay):
    """Starting 216 h before the decision time with the training statistic supplied gives identical decisions."""
    ts = max(TARGETS)
    ad = I.StreamingDecisionAdapter(I.agents_to_records(data.agents), *models)
    for _, batch in I.ReplayFeed(data.hourly, start=ts - pd.Timedelta(hours=I.WINDOW_HOURS - 1), end=ts):
        ad.ingest(batch)
    snap = ad.snapshot(hist_rate=engine.training_shortage_rate(data.hourly))
    assert I.compare_snapshots(snap, replay[1][ts])["match"]


def test_comparison_detects_a_changed_decision(replay, batch_engine):
    ts = max(TARGETS)
    tampered = replay[1][ts].copy()
    tampered.loc[0, "risk_level"] = "CRITICAL" if tampered.loc[0, "risk_level"] != "CRITICAL" else "LOW"
    assert not I.compare_snapshots(tampered, batch_engine.snapshot(ts))["match"]
    nudged = replay[1][ts].copy()
    nudged.loc[0, "risk_score"] += 0.01
    assert not I.compare_snapshots(nudged, batch_engine.snapshot(ts))["match"]


# ------------------------------------------------------------------ benchmark artifact integrity
def test_artifact_is_versioned_and_labelled(artifact):
    assert artifact["version"] == "phase2-integration-1"
    assert "not real upay production performance" in artifact["label"]
    assert "not real upay production performance" in artifact["benchmark"]["label"]
    assert artifact["contract"]["schema_version"] == "agentflow.feed.v1"
    assert artifact["contract"]["feed_event_fields"] == list(I.FeedEvent.model_fields)
    low = json.dumps(artifact).lower()
    for banned in ("production-ready", "production ready", "real-time guarantee", "proven at scale", "bank-grade", "roi"):
        assert banned not in low, banned
    assert any("Not real upay production performance" in x for x in artifact["limitations"])


def test_artifact_replay_evidence_is_complete(artifact):
    r = artifact["replay"]
    assert r["all_match"] and r["hist_shortage_rate_matches_batch"] and r["events_rejected"] == 0
    assert len(r["targets"]) >= 4 and all(t["match"] and t["max_abs_numeric_diff"] <= 1e-6 for t in r["targets"])
    assert all(t["replay_snapshot_digest"] == t["batch_snapshot_digest"] for t in r["targets"])
    assert r["events_validated"] == r["hours_replayed"] * r["agents"] and r["window_hours"] == I.WINDOW_HOURS
    assert "2026-08-31 13:00:00" in {t["timestamp"] for t in r["targets"]}  # the default demo decision time
    assert all(pd.Timestamp(t["timestamp"]) >= config.TEST_START for t in r["targets"])  # held-out period only


def test_benchmark_numbers_are_internally_consistent(artifact):
    b = artifact["benchmark"]
    runs = b["scales"]
    agents = [s["agents"] for s in runs]
    assert agents[:3] == [200, 1000, 5000] and agents == sorted(agents) and set(agents) <= {200, 1000, 5000, 10000}
    for s in runs:
        assert s["rows_in_window"] == s["agents"] * s["window_hours"] == s["agents"] * 216 and s["repeats"] >= 3
        med = s["median_seconds"]
        assert set(b["stages"]) <= set(med)
        assert all(isinstance(v, (int, float)) and math.isfinite(v) and v > 0 for v in med.values())
        assert all(s["min_seconds"][k] <= med[k] <= s["max_seconds"][k] for k in med)
        assert abs(s["hourly_refresh_seconds"] - sum(med[k] for k in b["stages"])) < 1e-3
        assert abs(s["agents_per_second_refresh"] - s["agents"] / s["hourly_refresh_seconds"]) < 0.2
        assert s["peak_rss_mb"] >= s["rss_after_model_load_mb"] > 0
    assert [s["rows_in_window"] for s in runs] == sorted(s["rows_in_window"] for s in runs)
    assert runs[-1]["hourly_refresh_seconds"] > runs[0]["hourly_refresh_seconds"]  # cost grows with scale (not hidden)
    assert runs[-1]["peak_rss_mb"] > runs[0]["peak_rss_mb"]
    assert len(b["bottlenecks"]) >= 3 and "not implemented" in " ".join(b["bottlenecks"])
    env = artifact["environment"]
    assert env["logical_cpus"] >= 1 and env["python"] and env["pandas"]


def test_benchmark_decisions_are_reproducible(artifact):
    """Re-run the smallest scale: timings differ run to run, but the decisions it measured must be identical."""
    out = subprocess.run([sys.executable, str(ROOT / "ml" / "scripts" / "integration_scale.py"), "--worker", "200",
                          "--repeats", "1"], capture_output=True, text=True, check=True, timeout=300)
    fresh = json.loads(out.stdout.strip().splitlines()[-1])
    recorded = next(s for s in artifact["benchmark"]["scales"] if s["agents"] == 200)
    assert fresh["decisions"] == recorded["decisions"] and fresh["rows_in_window"] == recorded["rows_in_window"]


# ------------------------------------------------------------------ API + UI
@pytest.fixture(scope="module")
def client():
    warnings.filterwarnings("ignore", category=DeprecationWarning)
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as c:
        yield c


def test_api_serves_evidence_and_schema_read_only(client, artifact):
    r = client.get("/api/integration-scale")
    assert r.status_code == 200 and r.json()["version"] == artifact["version"]
    assert client.post("/api/integration-scale").status_code == 405
    s = client.get("/api/integration/feed-schema").json()
    assert s["schema_version"] == "agentflow.feed.v1" and s["feed_event"]["additionalProperties"] is False


def test_ui_section_is_labelled_synthetic():
    web = ROOT / "apps" / "web" / "src"
    card = (web / "components" / "IntegrationScale.tsx").read_text()
    for phrase in ("Integration &amp; Scale", "Synthetic benchmark evidence — not real upay production performance.",
                   "not a live ledger, broker or real upay integration", "Bottleneck, reported honestly"):
        assert phrase.replace("&amp;", "&") in card, phrase
    page = (web / "app" / "impact" / "page.tsx").read_text()
    assert "<IntegrationScaleCard" in page and "/api/integration-scale" in page
    low = card.lower()
    assert "production-ready" not in low and "real-time" not in low and "NEXT_PUBLIC_" not in card
