"""API tests against the real service (trains models first if artifacts are missing)."""
import warnings

import pytest

warnings.filterwarnings("ignore", category=DeprecationWarning)
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok" and body["agents"] == 200
    assert "Synthetic" in body["data_label"]


def test_overview_kpis_consistent(client):
    d = client.get("/api/overview").json()
    k = d["kpis"]
    assert k["active_agents"] == 200
    assert sum(x["count"] for x in d["risk_distribution"]) == 200
    assert k["at_risk_agents"] == sum(x["count"] for x in d["risk_distribution"] if x["level"] in ("HIGH", "CRITICAL"))
    assert 0 <= k["projected_service_availability_pct"] <= 100
    assert k["projected_service_availability_after_plan_pct"] >= k["projected_service_availability_pct"]
    assert len(d["demand_trend"]) == 48


def test_agent_list_and_filters(client):
    d = client.get("/api/agents").json()
    assert d["count"] == 200
    scores = [a["risk_score"] for a in d["agents"]]
    assert scores == sorted(scores, reverse=True)
    crit = client.get("/api/agents", params={"risk_level": ["CRITICAL", "HIGH"], "cluster": "rural"}).json()
    assert all(a["risk_level"] in ("CRITICAL", "HIGH") and a["location_cluster"] == "rural" for a in crit["agents"])
    assert client.get("/api/agents", params={"risk_level": "BOGUS"}).status_code == 422
    assert client.get("/api/agents", params={"search": "<script>"}).status_code == 422


def test_agent_detail_contract(client):
    top = client.get("/api/agents").json()["agents"][0]
    d = client.get(f"/api/agents/{top['agent_id']}").json()
    for key in ("agent", "liquidity", "forecast", "risk", "explanation", "anomaly", "recommended_action", "history"):
        assert key in d
    assert 0 <= d["risk"]["risk_score"] <= 100
    assert d["risk"]["risk_score"] == pytest.approx(sum(d["risk"]["components"].values()), abs=0.11)
    assert d["explanation"] and all("text" in e and "evidence" in e for e in d["explanation"])
    assert d["history"][-1]["timestamp"].startswith(d["as_of"][:13])
    # no future target leaks into the "actual" history at as_of
    assert d["history"][-1]["future_6h_cash_demand"] is None
    f = client.get(f"/api/agents/{top['agent_id']}/forecast").json()
    assert f["forecast"]["pred_net_requirement_p90_6h"] >= f["forecast"]["pred_net_requirement_6h"]


def test_agent_errors_are_structured(client):
    r = client.get("/api/agents/AG-9999")
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"
    r = client.get("/api/agents/not-an-id")
    assert r.status_code == 400 and "error" in r.json()
    r = client.get("/api/overview", params={"as_of": "1999-01-01"})
    assert r.status_code == 400
    assert "Traceback" not in r.text


def test_recommendations_and_simulation(client):
    plan = client.get("/api/rebalancing/recommendations").json()
    assert plan["simulation_only"] is True
    recs = plan["recommendations"]
    assert recs
    for r in recs:
        assert r["source_cash_after"] >= r["source_protected_level"] - 1e-6
        assert r["destination_cash_after"] >= 0 and r["source_cash_after"] >= 0
    before = client.get("/api/overview").json()["kpis"]
    ids = [recs[0]["id"]]
    sim = client.post("/api/rebalancing/simulate", json={"reviewer_acknowledged": True, "recommendation_ids": ids, "reviewer_note": "test"})
    assert sim.status_code == 200
    s = sim.json()
    assert s["simulation_only"] is True and "no money moved" in s["status"]
    dest = [a for a in s["agents"] if a["role"] == "destination"][0]
    assert dest["risk_score_after"] <= dest["risk_score_before"]
    # simulation must not mutate the underlying state
    after = client.get("/api/overview").json()["kpis"]
    assert before == after
    audit = client.get("/api/rebalancing/audit").json()["simulations"]
    assert audit[0]["recommendation_ids"] == ids


def test_simulation_validation(client):
    assert client.post("/api/rebalancing/simulate", json={"reviewer_acknowledged": True, "recommendation_ids": []}).status_code == 422
    assert client.post("/api/rebalancing/simulate", json={"reviewer_acknowledged": True, "recommendation_ids": ["RB-999"]}).status_code == 404
    assert client.post("/api/rebalancing/simulate", json={"reviewer_acknowledged": True, "recommendation_ids": ["DROP TABLE"]}).status_code == 400
    assert client.post("/api/rebalancing/simulate", json={"reviewer_acknowledged": True, "recommendation_ids": ["RB-001"], "x": 1}).status_code == 422


def test_scenario_monotone(client):
    base = client.post("/api/scenario", json={"demand_shock_pct": 0}).json()
    shock = client.post("/api/scenario", json={"demand_shock_pct": 40}).json()
    assert shock["scenario"]["total_expected_shortfall"] >= base["scenario"]["total_expected_shortfall"]
    assert shock["scenario"]["at_risk_agents"] >= base["scenario"]["at_risk_agents"]
    assert client.post("/api/scenario", json={"demand_shock_pct": 500}).status_code == 422
    assert client.post("/api/scenario", json={"district": "Atlantis", "regional_shock_pct": 10}).status_code == 400


def test_impact_and_metrics(client):
    imp = client.get("/api/impact").json()
    assert imp["label"] == "Synthetic held-out simulation"
    assert {"status_quo", "agentflow", "naive_rebalancing"} <= set(imp["policies"])
    m = client.get("/api/model/metrics").json()
    assert m["label"] == "Synthetic held-out evaluation"
    assert "cash_demand" in m["metrics"]["forecast"]["targets"]
