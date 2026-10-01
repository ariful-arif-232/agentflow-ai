"""Forecast model training, inference and baseline evaluation tests."""
import numpy as np
import pytest

from agentflow import features, forecast


@pytest.fixture(scope="module")
def trained(small_features):
    train, test = features.time_split(small_features)
    bundle = forecast.train(train, max_iter=60)
    return bundle, train, test


def test_training_succeeds(trained):
    bundle, train, _ = trained
    assert set(bundle.models) == set(forecast.MODEL_SPECS)
    assert bundle.metadata["n_train_rows"] == len(train)
    assert bundle.metadata["train_end"] < str(features.config.TEST_START)


def test_saved_model_inference_roundtrip(trained, tmp_path):
    bundle, _, test = trained
    path = tmp_path / "m.joblib"
    bundle.save(path)
    loaded = forecast.ForecastBundle.load(path)
    a = bundle.predict(test.head(200))
    b = loaded.predict(test.head(200))
    assert np.allclose(a.to_numpy(), b.to_numpy())
    assert (a.to_numpy() >= 0).all()
    assert (a["pred_net_requirement_p90_6h"] >= a["pred_net_requirement_6h"]).all()


def test_baseline_and_ml_evaluation(trained):
    bundle, _, test = trained
    res = forecast.evaluate(bundle, test)
    for name in ("cash_demand", "net_requirement"):
        e = res["targets"][name]
        assert e["ml_model"]["mae"] > 0 and e["ml_model"]["rmse"] >= e["ml_model"]["mae"]
        assert set(e["baselines"]) == {"naive_yesterday", "seasonal_avg_7d"}
        assert all(b["n"] == e["ml_model"]["n"] for b in e["baselines"].values())
    # even a small model should beat the naive yesterday baseline on cash demand
    assert res["targets"]["cash_demand"]["improvement_vs_naive"]["mae_pct"] > 0
    assert 0.5 < res["quantile_p90"]["empirical_coverage"] <= 1.0


def test_regression_metrics_known_values():
    m = forecast.regression_metrics(np.array([10.0, 20.0]), np.array([12.0, 16.0]))
    assert m["mae"] == 3.0
    assert np.isclose(m["rmse"], np.sqrt((4 + 16) / 2))
    assert np.isclose(m["wape"], 6 / 30)
