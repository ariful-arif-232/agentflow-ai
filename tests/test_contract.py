"""API <-> frontend contract: fields the TypeScript types expect must exist in API responses."""
import re
import warnings
from pathlib import Path

import pytest

warnings.filterwarnings("ignore", category=DeprecationWarning)
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

TYPES = (Path(__file__).resolve().parents[1] / "apps" / "web" / "src" / "lib" / "types.ts").read_text()


def ts_fields(interface: str) -> set[str]:
    m = re.search(rf"export interface {interface}(?: extends [\w, ]+)? \{{(.*?)\n\}}", TYPES, re.S)
    assert m, f"interface {interface} not found"
    body = m.group(1)
    # top-level fields only (2-space indentation)
    return {f for f in re.findall(r"^  (\w+)\??:", body, re.M)}


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_agent_summary_contract(client):
    agent = client.get("/api/agents").json()["agents"][0]
    assert ts_fields("AgentSummary") <= set(agent)


def test_overview_contract(client):
    d = client.get("/api/overview").json()
    assert ts_fields("Overview") <= set(d)
    assert ts_fields("Meta") <= set(d)


def test_agent_detail_contract(client):
    aid = client.get("/api/agents").json()["agents"][0]["agent_id"]
    d = client.get(f"/api/agents/{aid}").json()
    assert ts_fields("AgentDetail") <= set(d)
    assert ts_fields("HistoryPoint") <= set(d["history"][0])


def test_plan_and_recommendation_contract(client):
    plan = client.get("/api/rebalancing/recommendations").json()
    assert ts_fields("Plan") <= set(plan)
    assert ts_fields("Recommendation") <= set(plan["recommendations"][0])
    assert ts_fields("PlanSummary") <= set(plan["summary"])


def test_impact_and_scenario_contract(client):
    assert ts_fields("ImpactResponse") <= set(client.get("/api/impact").json())
    assert ts_fields("MetricsResponse") <= set(client.get("/api/model/metrics").json())
    sc = client.post("/api/scenario", json={"demand_shock_pct": 10}).json()
    assert ts_fields("ScenarioResponse") <= set(sc)
    assert ts_fields("ScenarioSummary") <= set(sc["scenario"])


def test_simulation_contract(client):
    rid = client.get("/api/rebalancing/recommendations").json()["recommendations"][0]["id"]
    s = client.post("/api/rebalancing/simulate", json={"reviewer_acknowledged": True, "recommendation_ids": [rid]}).json()
    assert ts_fields("SimulationResult") <= set(s)
    assert ts_fields("Portfolio") <= set(s["portfolio_after"])
