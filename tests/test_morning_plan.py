"""Morning Liquidity Plan: artifact schema, live allocation, conservation, safety and API behaviour."""
import json
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "ml" / "artifacts" / "morning_plan_demo.json"
EVIDENCE = ROOT / "ml" / "artifacts" / "morning_plan_evidence.json"


@pytest.fixture(scope="module")
def client():
    from app.main import app
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def mp():
    from app.morning_plan import MorningPlanService
    return MorningPlanService()


# ---------------------------------------------------------------- artifacts
def test_fixture_schema_and_metadata():
    f = json.loads(FIXTURE.read_text())
    m = f["meta"]
    assert m["synthetic_data"] is True and m["simulation_only"] is True
    assert m["world_version"] == "dual-liquidity-world-v2" and m["assumptions_version"] == "2A.1" and m["seed"] == 2036
    assert m["frozen_model_spec_commit"] == "3128176e23b4a5a2dde883e8dff8a75f21e35540"
    assert m["source_research_commit"] == "c7418041f7b6c43873a8a45c1d43b32cafaf2a33"
    assert (m["information_cutoff"], m["allocation_time"], m["horizon"]) == ("07:00", "08:00", "08:00-23:59")
    assert len(f["dates"]) == 14 and sorted(f["dates"])[0] == "2026-08-18" and sorted(f["dates"])[-1] == "2026-08-31"
    assert [a["agent_id"] for a in f["agents"]] == sorted(a["agent_id"] for a in f["agents"])
    n = len(f["agents"])
    for day in f["dates"].values():
        assert set(day) == {"cash_p50", "cash_p90", "efloat_p50", "efloat_p90", "recommended_cash", "recommended_efloat"}
        assert all(len(v) == n for v in day.values())
        for r in ("cash", "efloat"):
            assert (np.array(day[f"{r}_p90"]) >= np.array(day[f"{r}_p50"])).all() and min(day[f"{r}_p50"]) >= 0


def test_fixture_contains_no_future_or_outcome_information():
    f = json.loads(FIXTURE.read_text())
    keys = set(f["meta"]) | {k for a in f["agents"] for k in a} | {k for d in f["dates"].values() for k in d}
    for token in ("future", "unmet", "oracle", "realised", "realized", "actual", "served", "requested", "requirement",
                  "outcome", "target"):
        assert not any(token in k.lower() for k in keys), token
    data_only = json.dumps({"agents": f["agents"], "dates": f["dates"]}).lower()
    assert "oracle" not in data_only and "unmet" not in data_only


def test_evidence_artifact_values_and_caveats():
    e = json.loads(EVIDENCE.read_text())
    assert e["synthetic_data"] is True and e["audit_seeds"] == [2036, 2037, 2038, 2039, 2040]
    assert e["worlds_improved"] == 5 and e["worlds_total"] == 5 and e["pre_registered_bar_passed"] is True
    assert e["combined_unmet_reduction_pct"]["median"] == pytest.approx(20.55, abs=0.01)
    assert e["combined_unmet_reduction_pct"]["min"] == pytest.approx(13.66, abs=0.01)
    assert e["combined_unmet_reduction_pct"]["max"] == pytest.approx(29.75, abs=0.01)
    assert e["cash_unmet_reduction_pct_median"] == pytest.approx(39.35, abs=0.01)
    assert e["efloat_unmet_reduction_pct_median"] == pytest.approx(9.70, abs=0.01)
    assert e["extra_working_capital_bdt"] == 0 and e["exact_resource_conservation"] is True
    assert e["pooled_p90_coverage"]["cash"] == pytest.approx(0.8517, abs=1e-4)
    assert "q90" in e["comparison"]
    caveats = " ".join(e["caveats"]).lower()
    for token in ("synthetic", "not real upay", "no guaranteed", "85%", "low-volume", "rural e-float", "human review"):
        assert token in caveats, token


# ---------------------------------------------------------------- allocator and plan
def test_live_allocation_conserves_every_district_exactly_and_matches_research(mp):
    for date in mp.dates:
        plan = mp.plan(date)
        assert plan["network"]["conserved"] and plan["network"]["extra_working_capital_bdt"] == 0
        assert plan["network"]["matches_frozen_research_allocation"] is True
        for r in ("cash", "efloat"):
            assert plan["network"][r]["difference_bdt"] == 0
            assert plan["network"][r]["status_quo_total_bdt"] == plan["network"][r]["recommended_total_bdt"]
        for d in plan["districts"]:
            assert d["cash_difference_bdt"] == 0 and d["efloat_difference_bdt"] == 0 and d["conserved"]
            agents = [a for a in plan["agents"] if a["district"] == d["district"]]
            assert sum(a["recommended_cash"] for a in agents) == d["cash_budget_bdt"]
            assert sum(a["recommended_efloat"] for a in agents) == d["efloat_budget_bdt"]


def test_floors_and_integer_allocations(mp):
    plan = mp.plan(mp.default_date)
    for a in plan["agents"]:
        for r in ("cash", "efloat"):
            assert isinstance(a[f"recommended_{r}"], int) and a[f"recommended_{r}"] >= 5_000
            assert a[f"{r}_delta"] == a[f"recommended_{r}"] - a[f"status_quo_{r}"]


def test_allocator_need_first_tie_break_and_floor_edge_case():
    from app.morning_plan import allocate_resource
    out = allocate_resource(60_000, np.array([10_000, 40_000, 40_000, 2_000]), np.array([20_000] * 4), 5_000)
    assert list(out) == [5_000, 40_000, 10_000, 5_000]  # tie on need -> lower index first
    edge = allocate_resource(12_000, np.array([9e4, 0, 0]), np.array([1, 1, 2]), 5_000)
    assert edge.sum() == 12_000 and list(edge) == [3_000, 3_000, 6_000]


def test_plan_is_deterministic(mp):
    from app.morning_plan import MorningPlanService
    other = MorningPlanService()
    assert json.dumps(other.plan(mp.default_date), sort_keys=True) == json.dumps(mp.plan(mp.default_date), sort_keys=True)


def test_explanations_are_deterministic_templates_with_evidence(mp):
    plan = mp.plan(mp.dates[0])
    for a in plan["agents"][:40]:
        ex = a["explanation"]
        assert set(ex) == {"cash", "efloat", "constraint", "safety"}
        for r, name in (("cash", "Physical cash"), ("efloat", "E-float")):
            assert ex[r].startswith(name)
            if a[f"{r}_delta"] > 0 and a[f"{r}_p90"] > a[f"status_quo_{r}"]:
                assert "exceeds the current morning allocation" in ex[r]
            if a[f"{r}_delta"] == 0:
                assert "unchanged" in ex[r]
        assert "5,000" in ex["constraint"] and "No automatic transfer" in ex["safety"]


def test_review_flags_follow_the_published_rules(mp):
    from app import morning_plan as m
    plan = mp.plan(mp.default_date)
    for a in plan["agents"]:
        codes = {f["code"] for f in a["review_flags"]}
        cut_e = -a["efloat_delta"]
        want_rural = a["location_cluster"] == "rural" and cut_e >= m.MEANINGFUL_CHANGE_BDT and cut_e >= 0.5 * a["status_quo_efloat"]
        assert ("rural_efloat_review" in codes) == want_rural
        want_p90 = any(a[f"recommended_{r}"] < a[f"{r}_p90"] for r in ("cash", "efloat"))
        assert ("p90_not_covered" in codes) == want_p90
        if "low_volume_review" in codes:
            assert a["agent_volume_segment"] == "low"
    focus = plan["review_focus"]
    assert focus["conserved"] is True and len(focus["largest_cuts"]) <= 5
    cuts = [max(-c["cash_delta"], -c["efloat_delta"]) for c in focus["largest_cuts"]]
    assert cuts == sorted(cuts, reverse=True)


def test_operational_response_has_no_future_fields(mp):
    from app.morning_plan import FORBIDDEN_FIELDS

    def keys(o):
        if isinstance(o, dict):
            for k, v in o.items():
                yield k
                yield from keys(v)
        elif isinstance(o, list):
            for v in o:
                yield from keys(v)
    for date in (mp.dates[0], mp.default_date):
        assert not any(t in k.lower() for k in keys(mp.plan(date)) for t in FORBIDDEN_FIELDS)


# ---------------------------------------------------------------- API
def test_dates_endpoint(client):
    j = client.get("/api/morning-plan/dates").json()
    assert len(j["dates"]) == 14 and j["default_date"] == "2026-08-31"
    assert j["synthetic_data"] is True and j["simulation_only"] is True
    assert set(j["labels"]) == {"synthetic", "human_review", "same_working_capital", "no_money_moves"}


def test_plan_endpoint_valid_invalid_and_malformed_dates(client):
    r = client.get("/api/morning-plan", params={"date": "2026-08-20"})
    assert r.status_code == 200 and r.json()["date"] == "2026-08-20"
    assert client.get("/api/morning-plan").json()["date"] == "2026-08-31"
    nf = client.get("/api/morning-plan", params={"date": "2026-01-01"})
    assert nf.status_code == 404 and nf.json()["error"]["code"] == "not_found"
    for bad in ("31-08-2026", "2026-08-31T08:00", "'; DROP", "x" * 30):
        r = client.get("/api/morning-plan", params={"date": bad})
        assert r.status_code == 422 and "error" in r.json() and "Traceback" not in r.text


def test_evidence_endpoint_is_labelled_synthetic(client):
    j = client.get("/api/morning-plan/evidence").json()
    assert j["synthetic_data"] is True and "not measured upay performance" in j["label"].lower()
    assert "not an expected saving" in j["display_note"]


def test_simulation_moves_no_money_and_is_audited(client):
    before = client.get("/api/morning-plan", params={"date": "2026-08-25"}).json()
    r = client.post("/api/morning-plan/simulate",
                    json={"date": "2026-08-25", "reviewer_acknowledged": True, "reviewer_note": "test"})
    s = r.json()
    assert r.status_code == 200 and s["status"] == "Simulation approved — no money moved."
    assert s["simulation_only"] is True and s["money_moved"] is False
    assert s["conservation"]["conserved"] is True and s["conservation"]["extra_working_capital_bdt"] == 0
    assert all(d["conserved"] for d in s["conservation"]["districts"])
    audit = client.get("/api/morning-plan/audit").json()["simulations"]
    assert audit[0]["simulation_id"] == s["simulation_id"] and audit[0]["date"] == "2026-08-25"
    after = client.get("/api/morning-plan", params={"date": "2026-08-25"}).json()
    assert after == before  # simulation does not change the plan or any state it is built from


def test_simulation_input_validation(client):
    assert client.post("/api/morning-plan/simulate", json={"date": "2026-08-25", "reviewer_acknowledged": False}).status_code == 400
    assert client.post("/api/morning-plan/simulate", json={"date": "2026-01-01", "reviewer_acknowledged": True}).status_code == 404
    assert client.post("/api/morning-plan/simulate", json={"date": "bad", "reviewer_acknowledged": True}).status_code == 422
    assert client.post("/api/morning-plan/simulate", json={"date": "2026-08-25", "reviewer_acknowledged": True,
                                                           "execute": True}).status_code == 422
    assert client.post("/api/morning-plan/simulate", json={"date": "2026-08-25", "reviewer_acknowledged": True,
                                                           "reviewer_note": "x" * 501}).status_code == 422


def test_missing_artifact_is_handled_safely(tmp_path):
    from app.morning_plan import MorningPlanService
    empty = MorningPlanService(tmp_path / "none.json", tmp_path / "none2.json")
    assert not empty.available and empty.default_date is None
    assert empty.evidence()["synthetic_data"] is True


def test_morning_plan_does_not_touch_the_legacy_engine_or_dual_world():
    src = (ROOT / "apps" / "api" / "app" / "morning_plan.py").read_text()
    for token in ("agentflow", "dual_world", "joblib", "parquet", "Engine"):
        assert token not in src, token
