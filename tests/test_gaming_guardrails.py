"""Agent-gaming guardrails: manufactured activity raises anomaly status and is never rewarded with liquidity.

Uses the trained Phase-1 detector and its unchanged thresholds on the synthetic dataset. No new fraud model.
The scenario: an at-risk agent (AG-0171 at the default demo time) inflates its own transactions to look
busier and attract peer cash.
"""
import json

import numpy as np
import pandas as pd
import pytest

from agentflow import anomaly, config, features, rebalance, rebalance_v2

AID = "AG-0171"
TS = pd.Timestamp("2026-08-31 13:00")


@pytest.fixture(scope="module")
def world():
    det = anomaly.AnomalyDetector.load()
    hourly = pd.read_parquet(config.DATASET_PATH)
    agents = pd.read_parquet(config.AGENTS_PATH)
    return det, hourly[hourly["agent_id"] == AID].copy(), agents[agents["agent_id"] == AID]


def _score(world, hours=0, count_mult=1.0, cash_out_mult=1.0, night=False):
    det, h, ag = world
    m = h.copy()
    if hours:
        w = m["timestamp"].between(TS - pd.Timedelta(hours=hours - 1), TS)
        for c in ("cash_out_count", "transaction_count"):
            m.loc[w, c] = (m.loc[w, c] * count_mult).round()
        m.loc[w, "cash_out_amount"] = m.loc[w, "cash_out_amount"] * cash_out_mult
    if night:  # heavy activity between 01:00 and 04:00 on the decision day
        day = m["timestamp"].dt.normalize() == TS.normalize()
        w = day & m["timestamp"].dt.hour.between(1, 4)
        total = int(h.loc[h["timestamp"].dt.normalize() == TS.normalize(), "transaction_count"].sum())
        m.loc[w, "transaction_count"] = round(0.03 * total)
        m.loc[w, "cash_out_count"] = round(0.02 * total)
    f = features.build_features(m, ag)
    s = det.score(anomaly.anomaly_features(f))
    window = f["timestamp"].between(TS - pd.Timedelta(hours=23), TS).to_numpy()  # engine's lookback: worst hour
    worst = float(s[window].max())
    at_ts = float(s[(f["timestamp"] == TS).to_numpy()][0])
    return worst, str(det.status(np.array([worst]))[0]), at_ts


def test_thresholds_are_the_unchanged_phase1_thresholds(world):
    det = world[0]
    assert (anomaly.WATCH_Q, anomaly.ANOMALOUS_Q) == (0.990, 0.997)
    assert det.thresholds["watch"] < det.thresholds["anomalous"] < 1.0


def test_manufactured_transaction_surge_raises_anomaly_status(world):
    base_score, base_status, _ = _score(world)
    assert base_status == "NORMAL"
    burst_score, burst_status, _ = _score(world, hours=4, count_mult=6.0, cash_out_mult=2.2)  # generator's rapid-burst range
    assert burst_status == "ANOMALOUS" and burst_score > base_score
    _, night_status, _ = _score(world, night=True)
    assert night_status == "ANOMALOUS"


def test_detection_has_limits_that_we_document(world):
    """Smaller manipulation scores higher but may stay below the review thresholds (honest limitation)."""
    base = _score(world)[2]
    mild = _score(world, hours=1, count_mult=2.0, cash_out_mult=1.5)
    strong = _score(world, hours=3, count_mult=5.0, cash_out_mult=2.0)
    assert base < mild[2] < strong[2]  # decision-hour score grows with the size of the manipulation
    assert mild[1] == "NORMAL" and strong[1] in ("WATCH", "ANOMALOUS")


@pytest.fixture(scope="module")
def demo_snapshot():
    from agentflow import engine
    return engine.Engine.load(serving=True).compact().snapshot(TS)


@pytest.mark.parametrize("policy", ["v1", "v2"])
def test_anomalous_at_risk_agent_is_held_and_never_rewarded(world, demo_snapshot, policy):
    snap = demo_snapshot.copy()
    assert snap.set_index("agent_id").loc[AID, "risk_level"] in ("HIGH", "CRITICAL")

    def plan(s):
        return rebalance.recommend(s) if policy == "v1" else rebalance_v2.recommend_v2(s, rebalance_v2.selected_config())

    honest = plan(snap)
    assert any(r["destination_agent"] == AID for r in honest["recommendations"])  # genuine need is supported (RB-013)

    _, status, _ = _score(world, hours=4, count_mult=6.0, cash_out_mult=2.2)
    gamed = snap.copy()
    gamed.loc[gamed["agent_id"] == AID, "anomaly_status"] = status  # status produced by the detector, not hand-set
    assert status == "ANOMALOUS"
    p = plan(gamed)
    assert all(r["destination_agent"] != AID and r["source_agent"] != AID for r in p["recommendations"])
    held = [h for h in p["held_for_review"] if h["agent_id"] == AID]
    assert len(held) == 1 and "manual review" in held[0]["reason"]
    assert "fraud" not in json.dumps(p).lower()
    assert AID not in {e["agent_id"] for e in p["escalations"]}  # not auto-escalated to the distributor either


def test_held_agents_have_no_approvable_recommendation(demo_snapshot):
    """Anything held for review has no recommendation id, so no approval (simulated or otherwise) can target it."""
    snap = demo_snapshot.copy()
    snap.loc[snap["risk_level"].isin(["HIGH", "CRITICAL"]), "anomaly_status"] = "ANOMALOUS"
    p = rebalance_v2.recommend_v2(snap, rebalance_v2.selected_config())
    assert p["recommendations"] == [] and len(p["held_for_review"]) > 0
