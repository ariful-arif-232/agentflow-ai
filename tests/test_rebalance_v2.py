"""Rebalancing policy V2: safety invariants, gate, determinism, V1 regression, evaluation protocol."""
import hashlib
import json
import warnings
from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from agentflow import config, impact, policy_selection, rebalance, rebalance_v2, risk
from test_rebalance import make_snapshot

CFG = rebalance_v2.RebalanceV2Config()


def _digest(plan: dict) -> str:
    return hashlib.sha256(json.dumps(plan, sort_keys=True, default=str).encode()).hexdigest()[:16]


# ------------------------------------------------------------------ V1 regression
@pytest.mark.parametrize("seed,legs,total,digest", [
    (3, 16, 615_500.0, "fdc9e1972ac0fb2b"),
    (5, 20, 643_000.0, "80c0bebf72ca1e07"),
])
def test_v1_behaviour_unchanged(seed, legs, total, digest):
    """Golden values recorded from V1 before V2 was introduced."""
    plan = rebalance.recommend(make_snapshot(n=60, seed=seed))
    assert len(plan["recommendations"]) == legs
    assert plan["summary"]["total_recommended_amount"] == total
    assert _digest(plan) == digest


# ------------------------------------------------------------------ building blocks
def test_risk_scalar_matches_vectorised_engine():
    rng = np.random.default_rng(1)
    n = 5000
    c, p50 = rng.uniform(0, 2e5, n), rng.uniform(0, 1.5e5, n)
    p50[::7] = rng.uniform(0, 900, len(p50[::7]))
    p90, v, h = p50 * rng.uniform(1, 2, n), rng.uniform(0, 3, n), rng.uniform(0, 0.3, n)
    v[::11] = np.nan
    ref = risk.compute_risk(c, p50, p90, v, h)
    got = [risk.risk_scalar(*x) for x in zip(c, p50, p90, v, h)]
    assert np.array_equal([g[0] for g in got], ref["risk_score"].to_numpy())
    assert [g[1] for g in got] == list(ref["risk_level"])


def test_leg_benefit_is_correct():
    b = rebalance_v2.leg_benefit(10_000, 30_000, 50_000, 70_000, 1.0, 0.0)
    s0, l0 = risk.risk_scalar(10_000, 50_000, 70_000, 1.0, 0.0)
    s1, l1 = risk.risk_scalar(40_000, 50_000, 70_000, 1.0, 0.0)
    assert (b["risk_score_before"], b["risk_level_before"], b["risk_score_after"], b["risk_level_after"]) == (s0, l0, s1, l1)
    assert b["shortfall_before"] == 40_000 and b["shortfall_after"] == 10_000 and b["shortfall_reduction"] == 30_000
    assert b["risk_drop"] == round(s0 - s1, 1)
    assert b["p90_coverage_before"] == pytest.approx(10 / 70) and b["p90_coverage_after"] == pytest.approx(40 / 70)


def test_donor_reserve_never_weaker_than_v1_and_grows_with_risk_signals():
    p50, p90 = np.array([20_000.0, 20_000.0, 20_000.0, 1_000.0]), np.array([30_000.0, 30_000.0, 30_000.0, 1_500.0])
    r = rebalance_v2.donor_reserve(p50, p90, [1.0, 2.0, 1.0, 1.0], [0.0, 0.0, 0.15, 0.0], CFG)
    v1 = rebalance.protected_level(p90)
    assert (r >= v1 - 1e-9).all()
    assert r[1] > r[0] and r[2] > r[0]  # busier / historically short donors keep more
    assert r[3] == CFG.donor_min_floor


# ------------------------------------------------------------------ plan invariants
@pytest.mark.parametrize("seed", range(8))
def test_v2_safety_invariants(seed):
    snap = make_snapshot(n=60, seed=seed)
    original = snap.copy(deep=True)
    plan = rebalance_v2.recommend_v2(snap, CFG)
    pd.testing.assert_frame_equal(snap, original)  # input snapshot immutable
    s = snap.set_index("agent_id")
    reserve = pd.Series(rebalance_v2.donor_reserve(s["pred_net_requirement_6h"], s["pred_net_requirement_p90_6h"],
                                                   s["velocity_ratio_3h"], s["hist_shortage_rate"], CFG), index=s.index)
    given = {}
    for r in plan["recommendations"]:
        src, dst = r["source_agent"], r["destination_agent"]
        assert r["policy"] == "v2"
        assert r["recommended_amount"] >= CFG.min_transfer and r["recommended_amount"] % CFG.round_to == 0
        assert r["distance_km"] <= CFG.max_distance_km and s.loc[src, "district"] == s.loc[dst, "district"]
        assert s.loc[src, "risk_level"] == "LOW" and s.loc[src, "anomaly_status"] != "ANOMALOUS"
        assert s.loc[dst, "risk_level"] in rebalance.TRIGGER_LEVELS
        given[src] = given.get(src, 0.0) + r["recommended_amount"]
    delta = rebalance.transfers_to_cash_delta(plan["recommendations"])
    assert abs(sum(delta.values())) < 1e-6  # same total network cash
    final = s["cash_balance"].copy()
    for a, d in delta.items():
        final[a] += d
    assert (final >= 0).all()  # no negative balances
    for src, amt in given.items():
        assert amt <= s.loc[src, "cash_balance"] - reserve[src] + 1e-6  # never above safe surplus
        assert final[src] >= reserve[src] - 1e-6  # dynamic reserve respected
        lvl = risk.risk_scalar(final[src], s.loc[src, "pred_net_requirement_6h"], s.loc[src, "pred_net_requirement_p90_6h"],
                               s.loc[src, "velocity_ratio_3h"], s.loc[src, "hist_shortage_rate"])[1]
        assert lvl == "LOW"  # donor never becomes HIGH/CRITICAL (stays LOW) after the complete plan
    for r in plan["recommendations"]:
        assert r["source_cash_after"] == pytest.approx(final[r["source_agent"]])
        assert r["donor_margin_after_plan"] == pytest.approx(final[r["source_agent"]] - reserve[r["source_agent"]], abs=0.01)


def test_v2_is_deterministic():
    a = rebalance_v2.recommend_v2(make_snapshot(n=60, seed=5), CFG)
    b = rebalance_v2.recommend_v2(make_snapshot(n=60, seed=5), CFG)
    assert a == b


def test_v2_every_leg_passes_the_benefit_gate_and_explains_itself():
    plan = rebalance_v2.recommend_v2(make_snapshot(n=60, seed=3), CFG)
    assert plan["recommendations"]
    for r in plan["recommendations"]:
        eb = r["expected_benefit"]
        dropped = risk.LEVEL_RANK[eb["risk_level_before"]] - risk.LEVEL_RANK[eb["risk_level_after"]]
        assert dropped >= 1 or eb["risk_score_before"] - eb["risk_score_after"] >= CFG.min_risk_drop or eb["shortfall_reduction_bdt"] > 0
        assert "Selected because" in r["reason"] and "protected reserve" in r["reason"]
        assert r["destination_risk_after"]["risk_score"] <= r["destination_risk_before"]["risk_score"]


def _two_agent_snapshot(donor_cash: float) -> pd.DataFrame:
    snap = pd.DataFrame({
        "agent_id": ["AG-0001", "AG-0002"], "district": ["Dhaka", "Dhaka"],
        "synthetic_latitude": [23.80, 23.81], "synthetic_longitude": [90.40, 90.41],
        "cash_balance": [10_000.0, donor_cash], "pred_net_requirement_6h": [100_000.0, 10_000.0],
        "pred_net_requirement_p90_6h": [150_000.0, 12_000.0], "velocity_ratio_3h": [1.0, 1.0],
        "hist_shortage_rate": [0.0, 0.0], "anomaly_status": ["NORMAL", "NORMAL"],
    })
    r = risk.compute_risk(snap["cash_balance"], snap["pred_net_requirement_6h"], snap["pred_net_requirement_p90_6h"],
                          snap["velocity_ratio_3h"], snap["hist_shortage_rate"])
    return snap.join(r)


def test_gate_rejects_negligible_transfer_and_escalates():
    snap = _two_agent_snapshot(donor_cash=18_000.0)  # donor reserve ~13.2k -> ~4.5k surplus: token amount
    assert snap.loc[0, "risk_level"] == "CRITICAL" and snap.loc[1, "risk_level"] == "LOW"
    plan = rebalance_v2.recommend_v2(snap, CFG)
    assert plan["recommendations"] == []
    assert plan["summary"]["n_gate_rejections"] == 1
    assert "minimum-benefit" in plan["escalations"][0]["reason"]
    # V1 would have moved the token amount
    assert len(rebalance.recommend(snap)["recommendations"]) == 1


def test_gate_accepts_material_transfer():
    plan = rebalance_v2.recommend_v2(_two_agent_snapshot(donor_cash=200_000.0), CFG)
    assert len(plan["recommendations"]) == 1
    eb = plan["recommendations"][0]["expected_benefit"]
    assert risk.LEVEL_RANK[eb["risk_level_before"]] > risk.LEVEL_RANK[eb["risk_level_after"]]


def test_anomalous_recipient_still_held_in_v2():
    snap = make_snapshot(n=60, seed=3)
    target = snap.sort_values("risk_score").iloc[-1]["agent_id"]
    snap.loc[snap["agent_id"] == target, "anomaly_status"] = "ANOMALOUS"
    plan = rebalance_v2.recommend_v2(snap, CFG)
    assert target not in {r["destination_agent"] for r in plan["recommendations"]}
    assert target in {h["agent_id"] for h in plan["held_for_review"]}


# ------------------------------------------------------------------ evaluation protocol
def test_policy_validation_folds_precede_test_period():
    policy_selection.assert_folds_before_test()
    assert all(f["val_end"] < config.TEST_START for f in policy_selection.FOLDS)
    starts = [f["val_start"] for f in policy_selection.FOLDS]
    assert starts == sorted(starts)  # chronological
    bad = ({"name": "X", "val_start": pd.Timestamp("2026-08-10"), "val_end": pd.Timestamp("2026-08-20")},)
    with pytest.raises(ValueError):
        policy_selection.assert_folds_before_test(bad)


def test_selected_config_comes_from_validation_artifact():
    sel = json.loads(rebalance_v2.SELECTION_PATH.read_text())
    assert sel["protocol"]["test_start"] == str(config.TEST_START)
    assert all(pd.Timestamp(f["val_end"]) < config.TEST_START for f in sel["protocol"]["folds"])
    cfg = rebalance_v2.selected_config()
    for k in rebalance_v2.RebalanceV2Config.tunable_fields():
        assert getattr(cfg, k) == sel["selected_config"][k]


def test_deployment_rule():
    v1 = {"unmet_avoided_bdt": 100.0, "unnecessary_interventions_pct": 20.0, "donor_shortage_events_after_transfer": 10,
          "unmet_avoided_per_1000_cost_bdt": 50.0}
    better = {**v1, "unmet_avoided_bdt": 98.0, "donor_shortage_events_after_transfer": 5, "unmet_avoided_per_1000_cost_bdt": 60.0}
    assert policy_selection.deployment_decision(v1, better)["default_policy"] == "v2"
    worse = {**better, "unmet_avoided_bdt": 80.0}  # gives up >5% of V1's benefit
    assert policy_selection.deployment_decision(v1, worse)["default_policy"] == "v1"
    unsafe = {**better, "donor_shortage_events_after_transfer": 11}
    assert policy_selection.deployment_decision(v1, unsafe)["default_policy"] == "v1"


@pytest.fixture(scope="module")
def small_impact_inputs(small_data, small_features, small_bundle):
    f = small_features
    usable = f["out_same_window_avg7"].notna() & f["out_rolling_mean_168h"].notna()
    preds = small_bundle.predict(f.loc[usable])
    train = f[(f["timestamp"] < config.TEST_START) & f["hour"].between(8, 21)]
    return f, small_data.agents, preds, train.groupby("agent_id")["liquidity_shortage"].mean()


def test_impact_comparison_is_deterministic_and_complete(small_impact_inputs):
    f, agents, preds, hist = small_impact_inputs
    cfg = replace(CFG, min_risk_drop=20.0)
    a = impact.run_impact(f, agents, preds, hist, v2_cfg=cfg)
    b = impact.run_impact(f, agents, preds, hist, v2_cfg=cfg)
    assert a["policies"] == b["policies"]
    assert {"status_quo", "naive_rebalancing", "agentflow", "agentflow_v2"} <= set(a["policies"])
    assert a["deployment_decision"]["default_policy"] in ("v1", "v2")
    for k in ("unmet_avoided_per_transfer_bdt", "unmet_avoided_per_1000_cost_bdt", "shortage_events_avoided_per_100_transfers",
              "escalated_need_bdt"):
        assert k in a["policies"]["agentflow_v2"]
    sim = impact.simulate_policy(f, agents, preds, hist, forecast_source="ml", policy="v2", policy_cfg=cfg)
    assert (sim["cash_end"] >= -1e-6).all()
    with pytest.raises(ValueError):
        impact.simulate_policy(f, agents, preds, hist, forecast_source="ml", policy="v3")


# ------------------------------------------------------------------ API
@pytest.fixture(scope="module")
def client():
    warnings.filterwarnings("ignore", category=DeprecationWarning)
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as c:
        yield c


def test_api_policy_selection(client):
    default = client.get("/api/rebalancing/recommendations").json()
    imp = json.loads((config.ARTIFACTS_DIR / "impact.json").read_text())
    assert default["policy"] == default["default_policy"] == imp["deployment_decision"]["default_policy"]
    v1 = client.get("/api/rebalancing/recommendations", params={"policy": "v1"}).json()
    v2 = client.get("/api/rebalancing/recommendations", params={"policy": "v2"}).json()
    assert v1["policy"] == "v1" and v2["policy"] == "v2"
    assert all(r.get("policy") == "v2" and "expected_benefit" in r for r in v2["recommendations"])
    assert all("expected_benefit" not in r for r in v1["recommendations"])
    assert client.get("/api/rebalancing/recommendations", params={"policy": "v9"}).status_code == 422
    rid = v1["recommendations"][0]["id"]
    sim = client.post("/api/rebalancing/simulate", json={"recommendation_ids": [rid], "policy": "v1"}).json()
    assert sim["policy"] == "v1" and sim["simulation_only"] is True
    assert client.post("/api/rebalancing/simulate", json={"recommendation_ids": [rid], "policy": "x"}).status_code == 422
