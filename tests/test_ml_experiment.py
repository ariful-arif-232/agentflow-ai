"""Phase-2 targeted ML experiment: leakage safety, held-out-safe selection, artifact integrity and the decision.

Synthetic controlled experiment. The serving forecast model is replaced only if a candidate passes every
pre-registered criterion.
"""
import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from agentflow import config, data_gen, features, forecast, ml_experiment as X

ROOT = Path(__file__).resolve().parents[1]
ART = json.loads((config.ARTIFACTS_DIR / "ml_experiment.json").read_text())
PREREG = json.loads((config.ARTIFACTS_DIR / "ml_experiment_preregistration.json").read_text())
METRICS = json.loads((config.ARTIFACTS_DIR / "metrics.json").read_text())
IMPACT = json.loads((config.ARTIFACTS_DIR / "impact.json").read_text())
CAND_COLS = X.SPATIAL_FEATURES + X.TEMPORAL_FEATURES
T0 = pd.Timestamp("2026-08-10 12:00")


@pytest.fixture(scope="module")
def data():
    d = data_gen.load()
    keep = d.hourly["timestamp"].between(pd.Timestamp("2026-07-25 00:00"), pd.Timestamp("2026-08-14 23:00"))
    return d.agents, d.hourly[keep].reset_index(drop=True)  # 21 days: enough history for every candidate feature


@pytest.fixture(scope="module")
def base(data):
    agents, hourly = data
    return X.add_candidate_features(features.build_features(hourly, agents), agents)


def _features(agents, hourly):
    return X.add_candidate_features(features.build_features(hourly, agents), agents)


def _same(a: pd.DataFrame, b: pd.DataFrame, mask) -> bool:
    return all(np.allclose(a.loc[mask, c].to_numpy(float), b.loc[mask, c].to_numpy(float), equal_nan=True) for c in CAND_COLS)


# ------------------------------------------------------------------ leakage
def test_candidate_features_ignore_the_future(data, base):
    """Scrambling every observation after T0 (including labels) leaves all candidate features at hours <= T0 unchanged."""
    agents, hourly = data
    h = hourly.copy()
    fut = h["timestamp"] > T0
    rng = np.random.default_rng(0)
    for c in ("cash_out_amount", "cash_in_amount", "unmet_cash_out", "cash_balance"):
        h.loc[fut, c] = h.loc[fut, c] * rng.uniform(0.2, 5.0, fut.sum())
    h.loc[fut, "transaction_count"] = h.loc[fut, "transaction_count"] * 7
    h.loc[fut, "liquidity_shortage"] = 1 - h.loc[fut, "liquidity_shortage"]
    h.loc[fut, "known_anomaly_label"] = 1
    f = _features(agents, h)
    past = (base["timestamp"] <= T0).to_numpy()
    assert _same(base, f, past)
    assert not _same(base, f, ~past)  # sanity: the perturbation is visible after T0


def test_neighbour_features_are_lagged_one_hour_and_exclude_self(data, base):
    agents, hourly = data
    aid = "AG-0171"
    district = agents.set_index("agent_id").loc[aid, "district"]
    h = hourly.copy()
    hit = (h["agent_id"] == aid) & (h["timestamp"] >= T0)
    h.loc[hit, ["cash_out_amount", "transaction_count"]] *= 10
    h.loc[hit, "liquidity_shortage"] = 1
    f = _features(agents, h)
    others = (f["agent_id"] != aid).to_numpy()
    at_t0 = (f["timestamp"] == T0).to_numpy()
    nbr = [c for c in CAND_COLS if c.startswith("nbr_")]
    for c in nbr:  # neighbours do not see the agent's hour-T0 data until T0 + 1
        assert np.allclose(base.loc[others & at_t0, c], f.loc[others & at_t0, c], equal_nan=True), c
    later = (f["timestamp"] == T0 + pd.Timedelta(hours=3)).to_numpy()
    same_d = (f["district"] == district).to_numpy() & others
    assert not np.allclose(base.loc[same_d & later, "nbr_district_out_regime"], f.loc[same_d & later, "nbr_district_out_regime"])
    own = (f["agent_id"] == aid).to_numpy()
    for c in ("nbr_district_out_regime", "nbr_district_velocity", "nbr_district_shortage_24h"):  # self excluded
        assert np.allclose(base.loc[own, c], f.loc[own, c], equal_nan=True), c


def test_candidate_code_never_reads_labels_or_future_targets_directly():
    src = (ROOT / "ml" / "agentflow" / "ml_experiment.py").read_text()
    start, end = src.index("def add_candidate_features"), src.index("CANDIDATES = {")
    body = src[start:end]
    for banned in ("known_anomaly_label", "anomaly_type", "shortage_next_6h", "unmet_next_6h", "future_6h_cash_demand",
                   "future_6h_cash_in", "shift(-"):
        assert banned not in body, banned
    # the only target use is the same-window history, lagged by whole days (as in the existing features)
    assert body.count("future_6h_net_cash_demand") == 1 and "shift(24 * d) for d in range(1, 8)" in body


# ------------------------------------------------------------------ held-out-safe selection
def test_validation_folds_are_purged_before_the_held_out_period():
    d = data_gen.load()
    f = features.build_features(d.hourly, d.agents)
    for fold in X.FOLDS:
        dev, val = X.fold_frames(f, fold)
        X.assert_selection_rows_before_test(dev, val)
        assert dev["timestamp"].max() + pd.Timedelta(hours=X.H) < fold["val_start"]
        assert val["timestamp"].max() + pd.Timedelta(hours=X.H) <= fold["val_end"] < config.TEST_START
    with pytest.raises(ValueError, match="held-out"):
        X.assert_selection_rows_before_test(f[f["timestamp"] == config.TEST_START - pd.Timedelta(hours=3)])


def test_preregistration_precedes_and_binds_the_held_out_run():
    assert PREREG["criteria_sha256"] == X.criteria_hash() == ART["criteria_sha256"]
    assert PREREG["held_out_rows_used"] == 0 and ART["preregistration"]["held_out_rows_used"] == 0
    assert all(pd.Timestamp(f["val_last_target_hour"]) < config.TEST_START for f in PREREG["folds"])
    assert pd.Timestamp(PREREG["written_at"]) <= pd.Timestamp(ART["generated_at"])
    assert ART["preregistration"]["selected_forecast_candidate"] == PREREG["selected_forecast_candidate"]
    assert ART["preregistration"]["selected_alert_threshold"] == PREREG["selected_alert_threshold"]


def test_selection_followed_the_preregistered_rules():
    v = PREREG["validation_forecast"]
    cur = v["current"]
    gate = {n: s["peak_requirement_mae"] <= 0.99 * cur["peak_requirement_mae"] and 0.87 <= s["p90_coverage"] <= 0.93
            and s["cash_demand_mae"] <= 1.01 * cur["cash_demand_mae"] for n, s in v.items() if n != "current"}
    assert {n: s["passes_validation_gate"] for n, s in v.items() if n != "current"} == gate
    chosen = min((n for n, ok in gate.items() if ok), key=lambda n: v[n]["peak_requirement_mae"], default=None)
    assert PREREG["selected_forecast_candidate"] == chosen
    th = PREREG["validation_alerts_current_model"]["thresholds"]
    assert PREREG["selected_alert_threshold"] == min(float(t) for t, x in th.items() if x["precision"] >= 0.70)
    assert v["spatial"]["peak_requirement_mae"] > cur["peak_requirement_mae"]  # the negative result is preserved


# ------------------------------------------------------------------ artifact integrity + decision
def test_current_arm_reproduces_the_published_phase1_metrics():
    cur = ART["results"]["current"]
    fc = METRICS["forecast"]
    assert cur["forecast"]["peak_requirement_mae"] == pytest.approx(fc["targets"]["net_requirement"]["ml_model"]["mae"], rel=1e-9)
    assert cur["forecast"]["cash_demand_mae"] == pytest.approx(fc["targets"]["cash_demand"]["ml_model"]["mae"], rel=1e-9)
    assert cur["forecast"]["seasonal_peak_mae"] == pytest.approx(fc["targets"]["net_requirement"]["baselines"]["seasonal_avg_7d"]["mae"], rel=1e-9)
    assert cur["forecast"]["p90_coverage"] == pytest.approx(fc["quantile_p90"]["empirical_coverage"], rel=1e-9)
    hi, ra = cur["alerts"]["thresholds"]["50"], METRICS["risk_alerts"]["variants"]["ml_forecast"]
    assert (hi["true_positives"], hi["false_positives"], hi["alerts"]) == (ra["true_positives"], ra["false_positives"], ra["alerts"])
    v2 = IMPACT["policies"]["agentflow_v2"]
    assert cur["v2"]["shortage_events"] == v2["shortage_events"]
    assert cur["v2"]["unmet_cash_demand_bdt"] == pytest.approx(v2["unmet_cash_demand_bdt"])
    assert cur["v2"]["donor_shortage_events_after_transfer"] == v2["donor_shortage_events_after_transfer"]


def test_decision_matches_the_numbers_and_the_criteria():
    c = X.CRITERIA["promotion_forecast"]
    cur, cand = ART["results"]["current"], ART["results"]["candidate"]
    d = ART["decisions"]["forecast"]
    exp = {
        "peak_mae_at_least_3pct_below_current": cand["forecast"]["peak_requirement_mae"] <= c["peak_mae_vs_current_max_ratio"] * cur["forecast"]["peak_requirement_mae"],
        "peak_mae_at_least_10pct_below_seasonal": 100 * (1 - cand["forecast"]["peak_requirement_mae"] / cand["forecast"]["seasonal_peak_mae"]) >= 10,
        "p90_coverage_in_range": 0.87 <= cand["forecast"]["p90_coverage"] <= 0.93,
        "v2_shortage_events_not_worse_than_2pct": cand["v2"]["shortage_events"] <= 1.02 * cur["v2"]["shortage_events"],
    }
    assert {k: d["checks"][k] for k in exp} == exp
    assert d["promoted"] == all(d["checks"].values())
    assert ART["serving_model_changed"] == d["promoted"]
    a = ART["decisions"]["alert_operating_point"]
    hi, op = cur["alerts"]["thresholds"]["50"], cur["alerts"]["thresholds"][f"{a['threshold']:g}"]
    assert a["checks"]["recall_gain_at_least_10pp"] == (100 * (op["recall"] - hi["recall"]) >= 10)
    assert a["checks"]["precision_at_least_0_70"] == (op["precision"] >= 0.70)
    assert a["promoted"] == all(a["checks"].values())
    assert "rebalancing recipients are unchanged" in a["scope"]
    # precision trade-off is reported honestly: lower thresholds raise recall and lower precision
    th = [cur["alerts"]["thresholds"][k] for k in ("50", "45", "40", "35", "30", "25")]
    assert all(th[i]["recall"] <= th[i + 1]["recall"] and th[i]["precision"] >= th[i + 1]["precision"] for i in range(5))


def test_rejected_candidate_leaves_the_serving_model_untouched():
    if ART["serving_model_changed"]:
        pytest.skip("a candidate was promoted")
    bundle = forecast.ForecastBundle.load()
    assert bundle.features == list(features.FORECAST_FEATURES)
    assert not set(CAND_COLS) & set(bundle.features)
    meta = json.loads((config.ARTIFACTS_DIR / "training_metadata.json").read_text())
    assert meta["features"] == list(features.FORECAST_FEATURES)
    assert METRICS["risk_alerts"]["alert_definition"] == "risk_level in {HIGH, CRITICAL}"


def test_artifact_is_versioned_and_labelled():
    assert ART["version"] == "phase2-ml-1" and "validation folds only" in ART["label"]
    assert set(ART["candidates"]) == set(X.CANDIDATES)
    low = json.dumps(ART).lower()
    assert "fraud" not in low and "real-world" not in low and "production-ready" not in low


# ------------------------------------------------------------------ API + UI
def test_api_and_model_health_card():
    warnings.filterwarnings("ignore", category=DeprecationWarning)
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as c:
        r = c.get("/api/ml-experiment")
        assert r.status_code == 200 and r.json()["version"] == ART["version"]
        assert c.post("/api/ml-experiment").status_code == 405
    web = ROOT / "apps" / "web" / "src"
    card = (web / "components" / "MlExperiment.tsx").read_text()
    for phrase in ("Targeted ML experiment", "Serving model unchanged", "Pre-registered rule", "not from a better model",
                   "Risk levels and rebalancing are unchanged", "held-out evaluated once"):
        assert phrase in card, phrase
    page = (web / "app" / "impact" / "page.tsx").read_text()
    assert "<MlExperimentCard" in page and "/api/ml-experiment" in page
