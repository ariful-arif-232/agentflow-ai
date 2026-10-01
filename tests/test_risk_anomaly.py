"""Risk engine and behavioural anomaly detector tests."""
import numpy as np
import pandas as pd
import pytest

from agentflow import anomaly, config, risk


def test_risk_score_bounded():
    rng = np.random.default_rng(0)
    n = 5000
    r = risk.compute_risk(rng.uniform(0, 300_000, n), rng.uniform(0, 300_000, n), rng.uniform(0, 400_000, n),
                          rng.uniform(0, 10, n), rng.uniform(0, 1, n))
    assert r["risk_score"].between(0, 100).all()
    assert set(r["risk_level"]) <= {"LOW", "MEDIUM", "HIGH", "CRITICAL"}


def test_extreme_inputs_bounded():
    r = risk.compute_risk([0, 1e12, 0], [1e12, 0, 0], [1e13, 0, 0], [1e6, np.nan, 0], [5, np.nan, 0])
    assert r["risk_score"].between(0, 100).all()
    assert r.loc[0, "risk_level"] == "CRITICAL"
    assert r.loc[2, "risk_level"] == "LOW"


def test_larger_deficit_never_lowers_risk():
    req, req90 = 60_000.0, 80_000.0
    cash = np.linspace(100_000, 0, 201)  # decreasing cash => increasing deficit
    s = risk.compute_risk(cash, req, req90, 1.2, 0.05)["risk_score"].to_numpy()
    assert np.all(np.diff(s) >= -1e-9)
    reqs = np.linspace(0, 200_000, 201)  # increasing requirement at fixed cash
    s2 = risk.compute_risk(30_000.0, reqs, reqs * 1.3, 1.0, 0.0)["risk_score"].to_numpy()
    assert np.all(np.diff(s2) >= -1e-9)


def test_risk_is_deterministic_and_documented_example():
    a = risk.compute_risk([29_600], [58_200], [70_000], [1.34], [0.08])
    b = risk.compute_risk([29_600], [58_200], [70_000], [1.34], [0.08])
    pd.testing.assert_frame_equal(a, b)
    assert a.loc[0, "risk_level"] == "HIGH"
    assert abs(a.loc[0, "coverage_ratio"] - 29_600 / 58_200) < 1e-9
    assert a.loc[0, "expected_shortfall"] == pytest.approx(28_600)


def test_explanations_come_from_evidence():
    r = risk.compute_risk([29_600], [58_200], [70_000], [1.34], [0.08]).iloc[0].to_dict()
    r.update({"pred_net_requirement_6h": 58_200, "pred_net_requirement_p90_6h": 70_000, "cash_balance": 29_600,
              "velocity_ratio_3h": 1.34, "hist_shortage_rate": 0.08, "is_salary_period": 1,
              "out_same_window_avg7": 90_000, "out_rolling_mean_168h": 10_000})
    reasons = risk.explain(r)
    codes = [x["code"] for x in reasons]
    assert codes[:2] == ["forecast_requirement", "coverage"]
    assert {"shortfall", "velocity", "history", "salary_period", "seasonal_window"} <= set(codes)
    text = " ".join(x["text"] for x in reasons)
    assert "BDT 58,200" in text and "BDT 29,600" in text and "51%" in text and "34%" in text
    # deterministic Bangla rendering of the same evidence
    assert all(x["text_bn"] and any("\u0980" <= ch <= "\u09ff" for ch in x["text_bn"]) for x in reasons)
    bn = " ".join(x["text_bn"] for x in reasons)
    assert "৳৫৮,২০০" in bn and "৳২৯,৬০০" in bn and "৫১%" in bn


@pytest.fixture(scope="module")
def detector_and_feats(small_features):
    af = anomaly.anomaly_features(small_features)
    train = small_features["timestamp"] < config.TEST_START
    return anomaly.AnomalyDetector().fit(af[train]), af, small_features


def test_anomaly_detector_separates_injected_anomalies(detector_and_feats):
    det, af, f = detector_and_feats
    test = f["timestamp"] >= config.TEST_START
    res = anomaly.evaluate(det, af[test], f.loc[test, "known_anomaly_label"], f.loc[test, "anomaly_type"])
    assert res["roc_auc"] > 0.85
    scores = det.score(af)
    assert ((scores >= 0) & (scores <= 1)).all()
    assert set(det.status(scores)) <= {"NORMAL", "WATCH", "ANOMALOUS"}


def test_anomaly_drivers_are_structured(detector_and_feats):
    det, af, f = detector_and_feats
    i = af.dropna().index[f.loc[af.dropna().index, "known_anomaly_label"] == 1][0]
    drivers = det.drivers(af.loc[i])
    assert 1 <= len(drivers) <= 3
    assert all({"feature", "description", "robust_z"} <= set(d) for d in drivers)
    assert all("fraud" not in d["description"].lower() for d in drivers)
