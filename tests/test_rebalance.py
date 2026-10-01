"""Rebalancing safety invariants."""
import numpy as np
import pandas as pd
import pytest

from agentflow import rebalance, risk


def make_snapshot(n=40, seed=0):
    rng = np.random.default_rng(seed)
    p50 = rng.uniform(5_000, 80_000, n)
    p90 = p50 * rng.uniform(1.1, 1.8, n)
    cash = rng.uniform(0, 150_000, n)
    snap = pd.DataFrame({
        "agent_id": [f"AG-{i:04d}" for i in range(n)],
        "district": rng.choice(["Dhaka", "Sylhet"], n),
        "synthetic_latitude": 23.8 + rng.uniform(-0.05, 0.05, n),
        "synthetic_longitude": 90.4 + rng.uniform(-0.05, 0.05, n),
        "cash_balance": cash, "pred_net_requirement_6h": p50, "pred_net_requirement_p90_6h": p90,
        "velocity_ratio_3h": rng.uniform(0.5, 2.0, n), "hist_shortage_rate": rng.uniform(0, 0.2, n),
        "anomaly_status": "NORMAL",
    })
    r = risk.compute_risk(snap["cash_balance"], p50, p90, snap["velocity_ratio_3h"], snap["hist_shortage_rate"])
    return snap.join(r)


@pytest.mark.parametrize("seed", range(8))
def test_rebalancing_invariants(seed):
    snap = make_snapshot(seed=seed)
    original = snap.copy(deep=True)
    cfg = rebalance.RebalanceConfig()
    plan = rebalance.recommend(snap, cfg)
    pd.testing.assert_frame_equal(snap, original)  # input never mutated
    s = snap.set_index("agent_id")
    prot = pd.Series(rebalance.protected_level(s["pred_net_requirement_p90_6h"], cfg), index=s.index)
    given = {}
    for r in plan["recommendations"]:
        src, dst = r["source_agent"], r["destination_agent"]
        assert r["recommended_amount"] >= cfg.min_transfer
        assert r["recommended_amount"] % cfg.round_to == 0
        assert r["distance_km"] <= cfg.max_distance_km
        assert s.loc[src, "district"] == s.loc[dst, "district"]
        assert s.loc[src, "risk_level"] == "LOW"
        assert s.loc[dst, "risk_level"] in rebalance.TRIGGER_LEVELS
        given[src] = given.get(src, 0.0) + r["recommended_amount"]
    for src, amt in given.items():
        safe_surplus = s.loc[src, "cash_balance"] - prot[src]
        assert amt <= safe_surplus + 1e-6  # never more than donor safe surplus
    final = s["cash_balance"].copy()
    for a, d in rebalance.transfers_to_cash_delta(plan["recommendations"]).items():
        final[a] += d
    assert (final >= 0).all()  # no negative balances
    for src in given:
        assert final[src] >= prot[src] - 1e-6  # donor reserve protected
    assert abs(sum(rebalance.transfers_to_cash_delta(plan["recommendations"]).values())) < 1e-6  # cash-neutral


def test_recipient_risk_improves_and_donor_stays_low():
    plan = rebalance.recommend(make_snapshot(n=60, seed=3))
    assert plan["recommendations"]
    for r in plan["recommendations"]:
        assert r["destination_risk_after"]["risk_score"] <= r["destination_risk_before"]["risk_score"]
        assert r["source_risk_after"]["risk_level"] in ("LOW", "MEDIUM")
        assert "protected level" in r["reason"]


def test_anomalous_agents_are_held_not_supported():
    snap = make_snapshot(n=60, seed=3)
    target = snap.sort_values("risk_score").iloc[-1]["agent_id"]
    snap.loc[snap["agent_id"] == target, "anomaly_status"] = "ANOMALOUS"
    plan = rebalance.recommend(snap)
    assert target not in {r["destination_agent"] for r in plan["recommendations"]}
    assert target in {h["agent_id"] for h in plan["held_for_review"]}


def test_recommendation_is_deterministic():
    a = rebalance.recommend(make_snapshot(seed=5))
    b = rebalance.recommend(make_snapshot(seed=5))
    assert a == b


def test_no_donor_means_escalation():
    snap = make_snapshot(n=20, seed=1)
    snap["cash_balance"] = 0.0
    r = risk.compute_risk(snap["cash_balance"], snap["pred_net_requirement_6h"], snap["pred_net_requirement_p90_6h"],
                          snap["velocity_ratio_3h"], snap["hist_shortage_rate"])
    snap[r.columns] = r
    plan = rebalance.recommend(snap)
    assert plan["recommendations"] == []
    assert plan["summary"]["n_escalations"] > 0
