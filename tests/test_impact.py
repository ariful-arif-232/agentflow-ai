"""Held-out impact simulation tests."""
import numpy as np
import pandas as pd
import pytest

from agentflow import config, features, impact


@pytest.fixture(scope="module")
def setup(small_data, small_features, small_bundle):
    f = small_features
    usable = f["out_same_window_avg7"].notna() & f["out_rolling_mean_168h"].notna()
    preds = small_bundle.predict(f.loc[usable])
    train = f[(f["timestamp"] < config.TEST_START) & f["hour"].between(8, 21)]
    hist = train.groupby("agent_id")["liquidity_shortage"].mean()
    return f, small_data.agents, preds, hist


def test_status_quo_replays_history_exactly(setup):
    f, agents, preds, hist = setup
    sim = impact.simulate_policy(f, agents, None, hist, forecast_source="none")
    test = f[f["timestamp"] >= config.TEST_START]
    assert np.isclose(sim["unmet"].sum(), test["unmet_cash_out"].sum())
    cash = test.pivot(index="timestamp", columns="agent_id", values="cash_balance")[sim["agent_ids"]].to_numpy()
    assert np.allclose(sim["cash_end"], cash)


def test_impact_is_deterministic_and_safe(setup):
    f, agents, preds, hist = setup
    a = impact.run_impact(f, agents, preds, hist)
    b = impact.run_impact(f, agents, preds, hist)
    assert a["policies"] == b["policies"]
    assert a["label"] == "Synthetic held-out simulation"
    sim = impact.simulate_policy(f, agents, preds, hist, forecast_source="ml")
    assert (sim["cash_end"] >= -1e-6).all()  # no negative balances anywhere
    # donors never give more than they hold at decision time (net of all their transfers that hour)
    idx = {a: i for i, a in enumerate(sim["agent_ids"])}
    given = {}
    for x in sim["log"]:
        key = (x["t"], x["source_agent"])
        given[key] = given.get(key, 0.0) + x["recommended_amount"]
    assert given, "expected at least one simulated transfer"
    for (t, src), amt in given.items():
        assert sim["cash_end"][t, idx[src]] - amt >= 0


def test_agentflow_does_not_increase_unmet_demand(setup):
    f, agents, preds, hist = setup
    res = impact.run_impact(f, agents, preds, hist)
    p = res["policies"]
    assert p["agentflow"]["unmet_cash_demand_bdt"] <= p["status_quo"]["unmet_cash_demand_bdt"]
    assert set(res["metric_definitions"]) >= {"shortage_events", "unmet_cash_demand_bdt", "service_availability_pct"}
    assert len(res["daily"]) == 14
