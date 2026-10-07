"""Monitoring is retrospective, deterministic and independent of serving decisions."""
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from agentflow import model_monitoring as M

ROOT = Path(__file__).resolve().parents[1]


def fixture_frame():
    ts = pd.date_range("2026-06-17", periods=500, freq="h")
    data = {"timestamp": ts}
    for i, name in enumerate(M.FEATURES):
        data[name] = np.tile(np.arange(10), 50) * (i + 1)
    return pd.DataFrame(data)


@pytest.mark.parametrize("value,expected", [(0, "STABLE"), (0.0999, "STABLE"), (0.1, "WATCH"),
                                             (0.2499, "WATCH"), (0.25, "DRIFT"), (None, "INSUFFICIENT_DATA")])
def test_threshold_boundaries(value, expected):
    assert M.status_for(value) == expected


def test_identical_distribution_is_stable_with_unequal_sample_sizes():
    ref = pd.Series(np.tile(np.arange(10), 100))
    cur = pd.Series(np.tile(np.arange(10), 20))
    out = M.feature_report(ref, cur, "out_last_1h")
    assert out["psi"] == 0 and out["status"] == "STABLE"
    assert sum(out["reference_fractions"]) == pytest.approx(1)
    assert sum(out["current_fractions"]) == pytest.approx(1)


@pytest.mark.parametrize("current", [0.0, 20.0])
def test_constant_reference_still_detects_shifts(current):
    out = M.feature_report(pd.Series([10.0] * 200), pd.Series([current] * 200), "out_last_1h")
    assert out["status"] == "DRIFT" and np.isfinite(out["psi"])
    assert M.feature_report(pd.Series([10.0] * 200), pd.Series([10.0] * 200), "out_last_1h")["psi"] == 0


def test_quality_counts_are_disjoint_and_invalid_values_not_imputed():
    values, q = M.values_and_quality(pd.Series([None, np.nan, np.inf, -np.inf, "bad", -2, 3.5, 5]), integer=True)
    assert q == {"rows": 8, "missing": 2, "invalid": 3, "out_of_range": 2, "valid": 1}
    assert values.tolist() == [5]


def test_empty_or_invalid_samples_are_never_called_stable():
    for current in (pd.Series([], dtype=float), pd.Series([np.nan] * 200), pd.Series([1.0] * 99)):
        result = M.feature_report(pd.Series([1.0] * 200), current, "out_last_1h")
        assert result["status"] == "INSUFFICIENT_DATA" and result["psi"] is None
        json.dumps(result, allow_nan=False)


def test_bins_use_reference_only_and_capture_out_of_training_range():
    ref = pd.Series(np.arange(200))
    stable = M.feature_report(ref, ref, "out_last_1h")
    shifted = M.feature_report(ref, ref + 10000, "out_last_1h")
    assert shifted["bin_edges"] == stable["bin_edges"]
    assert shifted["current_fractions"][-1] == 1 and shifted["status"] == "DRIFT"


def test_build_is_deterministic_nonmutating_and_uses_no_targets():
    frame = fixture_frame()
    before = frame.copy(deep=True)
    cut = frame.timestamp.iloc[350]
    a = M.build_report(frame, cut)
    b = M.build_report(frame, cut)
    assert json.dumps(a, sort_keys=True, allow_nan=False) == json.dumps(b, sort_keys=True, allow_nan=False)
    pd.testing.assert_frame_equal(frame, before)
    frame["future_6h_cash_demand"] = 999999
    frame["known_anomaly_label"] = 1
    assert M.build_report(frame, cut) == a
    assert a["warmup_rows_excluded"] == 168 and a["purge_rows_excluded"] == 6
    assert a["reference"]["rows"] == 176 and a["current"]["rows"] == 150
    assert pd.Timestamp(a["reference"]["end"]) < cut - pd.Timedelta(hours=6)


def test_missing_column_and_post_warmup_faults_are_not_hidden():
    frame = fixture_frame().drop(columns=["in_sum_6h"])
    frame.loc[380, "out_last_1h"] = np.nan
    out = M.build_report(frame, frame.timestamp.iloc[350])
    row = next(r for r in out["features"] if r["name"] == "in_sum_6h")
    assert out["missing_columns"] == ["in_sum_6h"] and row["status"] == "INSUFFICIENT_DATA"
    assert out["summary"]["quality_cells"]["current"]["missing"] == 151
    assert out["summary"]["human_review_recommended"]


@pytest.fixture
def api(tmp_path):
    spec = importlib.util.spec_from_file_location("monitoring_api_test", ROOT / "apps/api/app/model_monitoring.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.ARTIFACT_PATH = tmp_path / "model_monitoring.json"
    app = FastAPI()
    app.include_router(module.router)
    with TestClient(app) as client:
        yield client, module


def test_endpoint_is_read_only_and_does_not_assume_health_when_missing(api):
    client, module = api
    assert client.get("/api/model-monitoring").status_code == 404
    assert client.post("/api/model-monitoring").status_code == 405
    report = M.build_report(fixture_frame(), fixture_frame().timestamp.iloc[350])
    module.ARTIFACT_PATH.write_text(json.dumps(report), encoding="utf-8")
    before = module.ARTIFACT_PATH.read_bytes()
    response = client.get("/api/model-monitoring")
    assert response.status_code == 200 and response.json() == report
    assert module.ARTIFACT_PATH.read_bytes() == before


@pytest.mark.parametrize("content", ["not json", "[]", '{"version":"old","features":[]}', '{"version":"phase2-monitoring-1","features":[]}'])
def test_bad_artifact_is_explicitly_unavailable(api, content):
    client, module = api
    module.ARTIFACT_PATH.write_text(content, encoding="utf-8")
    res = client.get("/api/model-monitoring")
    assert res.status_code == 503 and res.json()["error"]["code"] == "monitoring_unavailable"


def test_real_artifact_is_generated_and_never_changes_existing_evidence():
    # Full repository CI runs the unchanged evaluation first, then the additive monitoring step.
    path = ROOT / "ml/artifacts/model_monitoring.json"
    assert path.exists(), "run_pipeline.py must generate monitoring evidence"
    report = json.loads(path.read_text())
    assert report["version"] == M.VERSION and len(report["features"]) == len(M.FEATURES)
    assert report["reference"]["rows"] > 100 and report["current"]["rows"] > 100
    assert "not live upay telemetry" in report["label"]
    assert "No automatic retraining" in report["action"]
    assert sum(report["summary"]["statuses"].values()) == 6
    assert all(r["name"] in M.FEATURES for r in report["features"])
    json.dumps(report, allow_nan=False)

    baseline = {p.name: p.read_bytes() for p in path.parent.glob("*.json") if p.name != path.name}
    before = path.read_bytes()
    subprocess.run([sys.executable, str(ROOT / "ml/scripts/model_monitoring.py")], check=True, capture_output=True, timeout=90)
    assert path.read_bytes() == before
    assert baseline == {p.name: p.read_bytes() for p in path.parent.glob("*.json") if p.name != path.name}
