"""Phase-2 logistics economics: cost proxy, V1/V2 integration, distributor hub proxy, API and claim safety."""
import json
import math
import warnings
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from agentflow import config, data_gen, logistics, rebalance, rebalance_v2, risk
from test_rebalance import make_snapshot

ROOT = Path(__file__).resolve().parents[1]
PARTS = ("base_handling_bdt", "distance_cost_bdt", "time_cost_bdt", "cash_in_transit_cost_bdt")
FORBIDDEN = ("real upay logistics cost", "proven roi", "real distributor saving", "measured customer saving")


# ------------------------------------------------------------------ cost proxy
def test_components_sum_exactly_to_total():
    rng = np.random.default_rng(0)
    for d, a in zip(rng.uniform(0, 15, 500), rng.uniform(0, 250_000, 500)):
        c = logistics.transfer_cost(d, a)
        assert round(sum(c[k] for k in PARTS), 2) == c["total_estimated_cost_bdt"]
        assert all(c[k] >= 0 for k in PARTS)
        assert c["assumption_label"] == logistics.ASSUMPTION_LABEL


def test_cost_formula_matches_documented_components():
    cfg = logistics.LogisticsCostConfig()
    c = logistics.transfer_cost(12.25, 38_500, cfg)
    billable = 12.25 * cfg.distance_multiplier
    assert c["billable_distance_km"] == pytest.approx(billable)
    assert c["distance_cost_bdt"] == pytest.approx(billable * cfg.per_km_operating_cost_bdt, abs=0.01)
    travel_min = billable / cfg.average_field_speed_kmh * 60
    assert c["travel_time_minutes"] == pytest.approx(travel_min, abs=0.05)
    assert c["time_cost_bdt"] == pytest.approx((travel_min + cfg.handling_time_minutes) / 60 * cfg.field_officer_cost_per_hour_bdt, abs=0.01)
    assert c["cash_in_transit_cost_bdt"] == pytest.approx(38_500 * cfg.cash_in_transit_bps / 10_000, abs=0.01)
    assert c["base_handling_bdt"] == cfg.base_handling_bdt


def test_zero_inputs_are_valid_and_invalid_inputs_are_rejected():
    c = logistics.transfer_cost(0, 0)
    assert c["distance_cost_bdt"] == 0 and c["cash_in_transit_cost_bdt"] == 0 and c["total_estimated_cost_bdt"] > 0
    for d, a in ((-1, 1000), (1, -1000), (math.nan, 1000), (1, math.inf)):
        with pytest.raises(ValueError):
            logistics.transfer_cost(d, a)
    with pytest.raises(ValueError):
        logistics.phase1_simple_cost(-0.1)
    for bad in ({"per_km_operating_cost_bdt": -1}, {"cash_in_transit_bps": -5}, {"average_field_speed_kmh": 0},
                {"distance_multiplier": 0.5}, {"base_handling_bdt": math.nan}):
        with pytest.raises(ValueError):
            logistics.LogisticsCostConfig(**bad)


def test_more_distance_never_costs_less():
    prev = None
    for d in np.linspace(0, 40, 81):
        c = logistics.transfer_cost(float(d), 20_000)
        if prev:
            for k in ("distance_cost_bdt", "time_cost_bdt", "travel_time_minutes", "total_estimated_cost_bdt"):
                assert c[k] >= prev[k]
        prev = c


def test_more_cash_moved_never_lowers_cash_in_transit_cost():
    prev = None
    for a in np.linspace(0, 500_000, 101):
        c = logistics.transfer_cost(5.0, float(a))
        if prev:
            assert c["cash_in_transit_cost_bdt"] >= prev["cash_in_transit_cost_bdt"]
            assert c["total_estimated_cost_bdt"] >= prev["total_estimated_cost_bdt"]
        prev = c


def test_assumptions_are_overridable_by_environment_without_code_changes():
    cfg = logistics.config_from_env({"AGENTFLOW_LOGISTICS_CASH_IN_TRANSIT_BPS": "25", "AGENTFLOW_LOGISTICS_PER_KM_OPERATING_COST_BDT": "18.5"})
    assert cfg.cash_in_transit_bps == 25 and cfg.per_km_operating_cost_bdt == 18.5
    assert cfg.base_handling_bdt == logistics.LogisticsCostConfig().base_handling_bdt
    assert logistics.config_from_env({}) == logistics.LogisticsCostConfig()
    with pytest.raises(ValueError):
        logistics.config_from_env({"AGENTFLOW_LOGISTICS_CASH_IN_TRANSIT_BPS": "ten"})
    with pytest.raises(ValueError):
        logistics.config_from_env({"AGENTFLOW_LOGISTICS_AVERAGE_FIELD_SPEED_KMH": "-3"})


def test_phase1_simple_cost_is_unchanged():
    assert logistics.phase1_simple_cost(12.25) == pytest.approx(456.25)
    assert logistics.phase1_simple_cost(0) == 150.0


# ------------------------------------------------------------------ distributor hub proxy
def test_distributor_proxy_uses_the_synthetic_district_hub_only():
    lat0, lon0 = data_gen.DISTRICTS["Rangpur"][:2]
    agent_lat, agent_lon = lat0 + 0.1, lon0 + 0.05
    c = logistics.replenishment_cost("Rangpur", agent_lat, agent_lon, 59_500)
    assert c["available"] and c["hub"] == "synthetic district hub"
    assert c["travel_distance_km"] == pytest.approx(float(rebalance.haversine_km(lat0, lon0, agent_lat, agent_lon)), abs=0.01)
    assert c["distance_multiplier"] == logistics.DEFAULT_CONFIG.distributor_distance_multiplier
    assert c["base_handling_bdt"] == logistics.DEFAULT_CONFIG.distributor_base_handling_bdt
    assert round(sum(c[k] for k in PARTS), 2) == c["total_estimated_cost_bdt"]
    assert "not the location of any real upay distributor" in c["hub_assumption"]
    assert logistics.district_hub("Rangpur") == (lat0, lon0)


def test_distributor_proxy_reports_unavailable_instead_of_guessing():
    assert logistics.replenishment_cost("Atlantis", 23.8, 90.4, 10_000) == {
        "available": False, "unavailable_reason": "missing synthetic_district_hub",
        "hub_assumption": logistics.HUB_ASSUMPTION, "assumption_label": logistics.ASSUMPTION_LABEL}
    c = logistics.replenishment_cost("Dhaka", None, math.nan, 10_000)
    assert not c["available"] and "agent_latitude" in c["unavailable_reason"] and "total_estimated_cost_bdt" not in c


# ------------------------------------------------------------------ V1 / V2 integration
@pytest.mark.parametrize("seed", range(4))
def test_every_transfer_and_escalation_carries_a_costed_breakdown(seed):
    snap = make_snapshot(n=60, seed=seed)
    for plan in (rebalance.recommend(snap), rebalance_v2.recommend_v2(snap)):
        for r in plan["recommendations"]:
            c = r["logistics_cost"]
            assert c["travel_distance_km"] == pytest.approx(r["distance_km"], abs=0.01)
            assert c["total_estimated_cost_bdt"] == pytest.approx(
                logistics.transfer_cost(r["distance_km"], r["recommended_amount"])["total_estimated_cost_bdt"], abs=0.5)
            assert abs(r["estimated_cost_bdt"] - logistics.phase1_simple_cost(r["distance_km"])) <= 0.65  # Phase-1 field kept
        for e in plan["escalations"]:
            assert e["replenishment_cost"]["available"]
            assert e["replenishment_cost"]["replenishment_amount_bdt"] == e["unresolved_need"]
        lg = plan["summary"]["logistics"]
        assert lg["peer_transfer_cost_bdt"] == pytest.approx(sum(r["logistics_cost"]["total_estimated_cost_bdt"] for r in plan["recommendations"]), abs=0.01)
        assert lg["total_operational_cost_bdt"] == pytest.approx(lg["peer_transfer_cost_bdt"] + lg["escalation_replenishment_cost_bdt"], abs=0.01)
        assert lg["assumption_label"] == logistics.ASSUMPTION_LABEL


def test_serving_v2_uses_phase1_ranking_and_logistics_ranking_is_explicit_only():
    cfg = rebalance_v2.selected_config()
    assert cfg.ranking_cost_model == "phase1_simple" == rebalance_v2.SERVING_RANKING_COST_MODEL
    assert rebalance_v2.RebalanceV2Config().ranking_cost_model == "phase1_simple"
    snap = make_snapshot(n=60, seed=2)
    old = rebalance_v2.recommend_v2(snap, cfg)
    new = rebalance_v2.recommend_v2(snap, replace(cfg, ranking_cost_model=rebalance_v2.EXPERIMENT_RANKING_COST_MODEL))
    for r in old["recommendations"]:  # serving plan is still costed with the richer proxy
        assert r["logistics_cost"]["assumption_label"] == logistics.ASSUMPTION_LABEL
    for r in new["recommendations"]:
        k = r["candidate_rank_key"]
        assert k["ranking_cost_model"] == "logistics_proxy"
        assert k["ranking_cost_bdt"] == pytest.approx(r["logistics_cost"]["total_estimated_cost_bdt"], abs=0.01)
    for r in old["recommendations"]:
        assert r["candidate_rank_key"]["ranking_cost_bdt"] == pytest.approx(logistics.phase1_simple_cost(r["distance_km"]), abs=0.15)
    with pytest.raises(ValueError):
        rebalance_v2.RebalanceV2Config(ranking_cost_model="cheapest")


@pytest.mark.parametrize("model", rebalance_v2.RANKING_COST_MODELS)
def test_donor_selection_is_deterministic_under_both_ranking_costs(model):
    cfg = replace(rebalance_v2.selected_config(), ranking_cost_model=model)
    snap = make_snapshot(n=60, seed=5)
    a = rebalance_v2.recommend_v2(snap, cfg)
    b = rebalance_v2.recommend_v2(snap.sample(frac=1.0, random_state=1).reset_index(drop=True), cfg)
    assert a == rebalance_v2.recommend_v2(make_snapshot(n=60, seed=5), cfg)
    key = lambda p: [(r["source_agent"], r["destination_agent"], r["recommended_amount"]) for r in p["recommendations"]]
    assert key(a) == key(b)  # row order of the snapshot does not change the plan


@pytest.mark.parametrize("model", rebalance_v2.RANKING_COST_MODELS)
@pytest.mark.parametrize("seed", range(6))
def test_all_donor_safety_constraints_hold_under_the_richer_cost(model, seed):
    cfg = replace(rebalance_v2.selected_config(), ranking_cost_model=model)
    snap = make_snapshot(n=60, seed=seed)
    snap.loc[snap.index[::9], "anomaly_status"] = "ANOMALOUS"
    plan = rebalance_v2.recommend_v2(snap, cfg)
    s = snap.set_index("agent_id")
    reserve = pd.Series(rebalance_v2.donor_reserve(s["pred_net_requirement_6h"], s["pred_net_requirement_p90_6h"],
                                                   s["velocity_ratio_3h"], s["hist_shortage_rate"], cfg), index=s.index)
    legs: dict[str, int] = {}
    for r in plan["recommendations"]:
        src, dst = r["source_agent"], r["destination_agent"]
        assert s.loc[src, "district"] == s.loc[dst, "district"] and r["distance_km"] <= cfg.max_distance_km
        assert s.loc[src, "risk_level"] == "LOW" and s.loc[src, "anomaly_status"] != "ANOMALOUS"
        assert s.loc[dst, "anomaly_status"] != "ANOMALOUS"
        assert r["expected_benefit"]["gate_reason"] and "below" not in r["expected_benefit"]["gate_reason"]  # gate passed
        legs[dst] = legs.get(dst, 0) + 1
    assert all(n <= cfg.max_donors_per_recipient for n in legs.values())
    final = s["cash_balance"].copy()
    for a, d in rebalance.transfers_to_cash_delta(plan["recommendations"]).items():
        final[a] += d
    assert (final >= 0).all()
    for src in {r["source_agent"] for r in plan["recommendations"]}:
        assert final[src] >= reserve[src] - 1e-6
        assert risk.risk_scalar(final[src], s.loc[src, "pred_net_requirement_6h"], s.loc[src, "pred_net_requirement_p90_6h"],
                                s.loc[src, "velocity_ratio_3h"], s.loc[src, "hist_shortage_rate"])[1] == "LOW"
    held = {h["agent_id"] for h in plan["held_for_review"]}
    assert held <= set(s.index[s["anomaly_status"] == "ANOMALOUS"])


def test_policy_selection_protocol_still_uses_the_phase1_cost():
    from agentflow import policy_selection
    assert all(c.ranking_cost_model == "phase1_simple" for c in policy_selection.grid_configs())


# ------------------------------------------------------------------ Phase-1 evidence and Phase-2 artifact
IMPACT = json.loads((config.ARTIFACTS_DIR / "impact.json").read_text())


def test_phase1_metrics_remain_intact():
    p = IMPACT["policies"]
    assert (p["status_quo"]["shortage_events"], p["status_quo"]["unmet_cash_demand_bdt"]) == (2017, 9_536_930.0)
    assert (p["agentflow"]["shortage_events"], p["agentflow"]["interventions"], p["agentflow"]["donor_shortage_events_after_transfer"]) == (1255, 501, 25)
    v2 = p["agentflow_v2"]
    assert (v2["shortage_events"], v2["unmet_cash_demand_bdt"], v2["interventions"], v2["donor_shortage_events_after_transfer"]) == (1223, 5_690_940.0, 345, 14)
    assert v2["estimated_logistics_cost_bdt"] == 115_357.0  # Phase-1 cost definition unchanged
    assert round(IMPACT["agentflow_v2_vs_status_quo"]["shortage_events_reduction_pct"], 1) == 39.4
    assert round(IMPACT["agentflow_v2_vs_status_quo"]["unmet_demand_reduction_pct"], 1) == 40.3
    assert IMPACT["deployment_decision"]["default_policy"] == "v2"


def test_phase2_block_is_versioned_labelled_and_consistent():
    p2 = IMPACT["phase2_logistics"]
    assert p2["version"] == "phase2-logistics-2" and "not upay measured cost" in p2["label"]
    assert p2["serving_v2_ranking_cost_model"] == "phase1_simple" and p2["experiment_ranking_cost_model"] == "logistics_proxy"
    assert p2["experiment_status"].startswith("EXPERIMENTAL — not adopted")
    assert p2["assumptions"]["assumption_label"] == logistics.ASSUMPTION_LABEL
    ch = p2["v2_ranking_change"]
    for k, v in ch["phase1_ranking"].items():
        assert v == IMPACT["policies"]["agentflow_v2"].get(k)
    for name, m in p2["policies"].items():
        assert round(sum(m["peer_cost_components_bdt"].values()), 2) == pytest.approx(m["peer_transfer_logistics_cost_bdt"], abs=0.02)
        assert m["total_operational_logistics_cost_proxy_bdt"] == pytest.approx(
            m["peer_transfer_logistics_cost_bdt"] + m["distributor_escalation_cost_proxy_bdt"], abs=0.02)
        assert m["distributor_escalation_events_unavailable"] == 0
    assert p2["policies"]["agentflow_v2"]["interventions"] == IMPACT["policies"]["agentflow_v2"]["interventions"]
    exp = p2["policies"]["agentflow_v2_logistics_ranking_experiment"]
    assert exp["shortage_events"] == ch["logistics_proxy_ranking"]["shortage_events"] == 1229


# ------------------------------------------------------------------ API and claim safety
@pytest.fixture(scope="module")
def client():
    warnings.filterwarnings("ignore", category=DeprecationWarning)
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as c:
        yield c


def test_api_exposes_the_assumption_label(client):
    a = client.get("/api/logistics/assumptions").json()
    assert a["assumption_label"] == logistics.ASSUMPTION_LABEL and a["simulation_only"] is True
    assert "governed operator rates" in a["deployment_note"] and a["v2_ranking_cost_model"] == "phase1_simple"
    for policy in ("v1", "v2"):
        plan = client.get(f"/api/rebalancing/recommendations?policy={policy}").json()
        assert plan["summary"]["logistics"]["assumption_label"] == logistics.ASSUMPTION_LABEL
        assert all(r["logistics_cost"]["assumption_label"] == logistics.ASSUMPTION_LABEL for r in plan["recommendations"])
        assert all("not the location of any real upay distributor" in e["replenishment_cost"]["hub_assumption"] for e in plan["escalations"])
    rid = client.get("/api/rebalancing/recommendations").json()["recommendations"][0]["id"]
    sim = client.post("/api/rebalancing/simulate", json={"reviewer_acknowledged": True, "recommendation_ids": [rid]}).json()
    assert sim["simulation_only"] is True and sim["logistics_assumption_label"] == logistics.ASSUMPTION_LABEL
    assert client.get("/api/impact").json()["phase2_logistics"]["assumptions"]["assumption_label"] == logistics.ASSUMPTION_LABEL


def test_no_real_or_upay_cost_claim_appears(client):
    texts = [json.dumps(client.get(u).json()).lower() for u in
             ("/api/logistics/assumptions", "/api/rebalancing/recommendations", "/api/impact")]
    for p in [*(ROOT / "apps/web/src").rglob("*.tsx"), ROOT / "ml/agentflow/logistics.py", ROOT / "README.md",
              ROOT / "docs/EVALUATION.md", ROOT / "docs/PROJECT_REPORT.md"]:
        texts.append(p.read_text().lower())
    for t in texts:
        for phrase in FORBIDDEN:
            assert phrase not in t, phrase
    ui = (ROOT / "apps/web/src/components/LogisticsCost.tsx").read_text()
    assert "Simulated operational-cost proxy — replace assumptions with governed operator rates for deployment." in ui
