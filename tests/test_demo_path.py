"""Judge demo path: defaults, V2 evidence, simulation-only semantics and claim-safe UI wording."""
import json
import re
import warnings
from pathlib import Path

import pytest

warnings.filterwarnings("ignore", category=DeprecationWarning)
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
WEB_SRC = ROOT / "apps" / "web" / "src"
DEMO_AGENT = "AG-0171"


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_demo_defaults_snapshot_and_policy(client):
    """The 'Reset demo' control restores these server-provided defaults (client-side only)."""
    t = client.get("/api/meta/time").json()
    assert t["default_as_of"] == "2026-08-31T13:00:00"
    assert t["default_as_of"] in t["available"]
    plan = client.get("/api/rebalancing/recommendations").json()
    assert plan["policy"] == plan["default_policy"] == "v2"
    assert client.get("/api/overview").json()["kpis"]["rebalancing_policy"] == "v2"


def test_demo_agent_story_is_backed_by_live_outputs(client):
    d = client.get(f"/api/agents/{DEMO_AGENT}").json()
    assert d["risk"]["risk_level"] in ("HIGH", "CRITICAL")
    assert d["forecast"]["expected_shortfall"] > 0  # "without action" strip has something to show
    assert d["liquidity"]["cash_balance"] > 0  # still has cash: risk is flagged before customers are affected
    assert any(e["code"] == "coverage" for e in d["explanation"])
    assert all(e["text_bn"] for e in d["explanation"])  # Bangla explanation still available
    recs = d["recommendations"]["as_destination"]
    assert recs, "demo agent should receive a V2 recommendation at the default snapshot"
    r = recs[0]
    assert r["policy"] == "v2" and r["expected_benefit"]["gate_reason"]
    assert r["source_risk_after"]["risk_level"] == "LOW"
    assert r["donor_margin_after_plan"] >= 0
    assert r["destination_risk_after"]["risk_score"] < r["destination_risk_before"]["risk_score"]
    assert {"covers_remaining_need", "risk_points_per_bdt100_cost"} <= set(r["candidate_rank_key"])


def test_approve_simulation_is_simulation_only_and_audited(client):
    rid = client.get(f"/api/agents/{DEMO_AGENT}").json()["recommendations"]["as_destination"][0]["id"]
    before = client.get("/api/overview").json()["kpis"]
    s = client.post("/api/rebalancing/simulate", json={"reviewer_acknowledged": True, "recommendation_ids": [rid], "reviewer_note": "demo"}).json()
    assert s["simulation_only"] is True
    assert "no money moved" in s["status"].lower()
    assert s["policy"] == "v2"
    assert client.get("/api/rebalancing/audit").json()["simulations"][0]["simulation_id"] == s["simulation_id"]
    assert client.get("/api/overview").json()["kpis"] == before  # nothing in the live state changed


def test_policy_comparison_fields_for_impact_page(client):
    imp = client.get("/api/impact").json()
    assert imp["label"] == "Synthetic held-out simulation"
    assert imp["deployment_decision"]["default_policy"] == "v2"
    for k in ("agentflow", "agentflow_v2"):
        m = imp["policies"][k]
        for f in ("unmet_cash_demand_bdt", "interventions", "donor_shortage_events_after_transfer",
                  "estimated_logistics_cost_bdt", "unnecessary_interventions_pct"):
            assert isinstance(m[f], (int, float))
    v1, v2 = imp["policies"]["agentflow"], imp["policies"]["agentflow_v2"]
    # the honest limitation shown on the Impact page must stay true for the committed artifacts
    assert v2["unnecessary_interventions_pct"] > v1["unnecessary_interventions_pct"]
    assert round(v2["unnecessary_interventions_pct"] * v2["interventions"] / 100) < round(
        v1["unnecessary_interventions_pct"] * v1["interventions"] / 100)


def _ui_text() -> str:
    return "\n".join(p.read_text() for p in WEB_SRC.rglob("*.tsx"))


def test_ui_never_claims_money_moved_or_fraud():
    text = _ui_text().lower()
    for phrase in ("transfer completed", "money transferred", "payment sent", "fraud detected", "confirmed fraud",
                   "real upay data", "production data"):
        assert phrase not in text, phrase
    assert "simulation only — no money moves" in text
    assert "simulation approved" in text


def test_ui_has_resilient_error_state_and_demo_controls():
    ui = (WEB_SRC / "components" / "ui.tsx").read_text()
    assert "Live decision service is temporarily unavailable." in ui and "Retry" in ui
    api = (WEB_SRC / "lib" / "api.ts").read_text()
    assert re.search(r"REQUEST_TIMEOUT_MS\s*=\s*\d", api) and "AbortController" in api
    shell = (WEB_SRC / "components" / "Shell.tsx").read_text()
    assert "Reset demo" in shell and "Judge demo" in shell and "ServiceGate" in shell
    guide = (WEB_SRC / "components" / "DemoGuide.tsx").read_text()
    assert f'DEMO_AGENT = "{DEMO_AGENT}"' in guide
    demo_doc = (ROOT / "docs" / "DEMO_SCRIPT.md").read_text()
    assert DEMO_AGENT in demo_doc


def test_committed_artifacts_match_documented_headline():
    imp = json.loads((ROOT / "ml" / "artifacts" / "impact.json").read_text())
    v1, v2 = imp["policies"]["agentflow"], imp["policies"]["agentflow_v2"]
    assert (v1["interventions"], v1["donor_shortage_events_after_transfer"]) == (501, 25)
    assert (v2["interventions"], v2["donor_shortage_events_after_transfer"]) == (345, 14)
