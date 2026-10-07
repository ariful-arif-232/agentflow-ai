"""Phase-2 business-impact layer: formulas, assumptions, edge cases, methodology, API, determinism and evidence preservation."""
import json
import math
import warnings
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from agentflow import business_impact as bi
from agentflow import config, data_gen

ROOT = Path(__file__).resolve().parents[1]
LABEL = "Synthetic simulated estimate — not measured upay performance."
BIZ = json.loads((config.ARTIFACTS_DIR / "business_impact.json").read_text())
IMPACT = json.loads((config.ARTIFACTS_DIR / "impact.json").read_text())
FORBIDDEN = ("real upay revenue", "real upay commission", "proven roi", "guaranteed", "real customer transactions were saved",
             "measured customer saving", "upay's commission rate is", "actual upay commission")


# ------------------------------------------------------------------ hand-built simulations
def _sim(unmet, out_req, log=(), esc=()):
    hours = pd.date_range("2026-08-18 09:00", periods=len(unmet), freq="h")
    return {"hours": hours, "agent_ids": ["AG-0001", "AG-0002"], "unmet": np.array(unmet, float),
            "out_req": np.array(out_req, float), "log": list(log), "escalation_log": list(esc)}


def _leg(amount, cost):
    return {"recommended_amount": amount, "logistics_cost": {"total_estimated_cost_bdt": cost}}


OUT = [[10_000, 4_000], [6_000, 0]]
COUNTS = np.array([[5, 2], [3, 0]])
CLUSTER = np.array([[2_000.0, 1_000.0]])


def _sims():
    return {
        "status_quo": _sim([[4_000, 2_000], [2_000, 0]], OUT),
        "agentflow_v1": _sim([[2_000, 0], [0, 0]], OUT, [_leg(5_000, 300.0), _leg(2_000, 200.0)],
                             [{"t": 0, "agent_id": "AG-0002", "unresolved_need": 3_000.0, "cost_bdt": 900.0},
                              {"t": 1, "agent_id": "AG-0002", "unresolved_need": 2_000.0, "cost_bdt": 800.0}]),
        "agentflow_v2": _sim([[2_000, 0], [0, 0]], OUT, [_leg(5_000, 250.0)]),
    }


def test_formulas_on_a_hand_checked_example():
    out = bi.compute(_sims(), COUNTS, CLUSTER, bi.BusinessAssumptions(agent_commission_bps=100))
    sq = out["calculations"]["policies"]["status_quo"]["customer"]
    assert sq["requested_cash_out_bdt"] == 20_000 and sq["unmet_cash_out_bdt"] == 8_000
    assert sq["served_cash_out_bdt"] == 12_000 and sq["demand_fill_rate_pct"] == pytest.approx(60.0)
    assert sq["requested_cash_out_transactions"] == 10 and sq["shortage_agent_hours"] == 3
    # Method A tickets: 2,000 · 2,000 / 2,000 · cluster 1,000 (no counted transaction in that hour)
    assert sq["estimated_failed_transactions"] == pytest.approx(4_000 / 2_000 + 2_000 / 2_000 + 2_000 / 2_000)
    assert sq["estimated_failed_transactions_method_b"] == pytest.approx(4_000 / 2_000 + 2_000 / 1_000 + 2_000 / 2_000)
    v1 = out["calculations"]["vs_status_quo"]["agentflow_v1"]
    assert v1["customer"]["cash_out_value_protected_bdt"] == 6_000
    assert v1["customer"]["estimated_transactions_protected"] == pytest.approx(4.0 - 1.0)
    assert v1["customer"]["estimated_transactions_protected_range"] == [pytest.approx(3.0), pytest.approx(4.0)]
    assert v1["agent"]["illustrative_commission_protected_bdt"] == pytest.approx(60.0)  # 6,000 × 100 bps
    e = v1["economics"]["peer_transfers_only"]
    assert e["operational_logistics_cost_bdt"] == 500.0 and e["net_illustrative_value_bdt"] == pytest.approx(-440.0)
    assert e["benefit_cost_ratio"] == pytest.approx(60 / 500)
    assert e["break_even_commission_bps"] == pytest.approx(500 / 6_000 * 10_000)
    ops = out["calculations"]["policies"]["agentflow_v1"]["operations"]
    assert ops["peer_transfers"] == 2 and ops["average_cost_per_peer_transfer_bdt"] == 250.0
    assert ops["escalation_events"] == 2 and ops["escalated_agent_days"] == 1  # same agent, same day → one trip
    assert ops["distributor_cost_proxy_every_escalation_bdt"] == 1_700.0
    assert ops["distributor_cost_proxy_one_trip_per_agent_day_bdt"] == 900.0
    assert v1["distributor"]["break_even_fee_per_trip_bdt"] == 900.0 and v1["distributor"]["illustrative_margin_bdt"] is None
    assert v1["economics"]["including_distributor_trips"]["operational_logistics_cost_bdt"] == 1_400.0


def test_break_even_rate_exactly_covers_the_cost():
    e = bi.economics(3_837_640, 208_611.9, 50)
    at_be = bi.economics(3_837_640, 208_611.9, e["break_even_commission_bps"])
    assert at_be["net_illustrative_value_bdt"] == pytest.approx(0, abs=0.01)
    assert at_be["benefit_cost_ratio"] == pytest.approx(1.0)


def test_distributor_margin_only_with_a_supplied_fee():
    a = bi.BusinessAssumptions(distributor_fee_per_trip_bdt=1_000)
    d = bi.compute(_sims(), COUNTS, CLUSTER, a)["calculations"]["vs_status_quo"]["agentflow_v1"]["distributor"]
    assert d["illustrative_margin_bdt"] == pytest.approx(1_000 * 1 - 900) and d["margin_note"] is None


# ------------------------------------------------------------------ edge cases
def test_no_divide_by_zero():
    for value, cost in ((0, 0), (0, 500), (1_000, 0), (-50, 10)):
        e = bi.economics(value, cost, 50)
        assert all(v is None or math.isfinite(v) for v in e.values())
    assert bi.economics(1_000, 0, 50)["benefit_cost_ratio"] is None
    assert bi.economics(0, 500, 50)["break_even_commission_bps"] is None
    zero = _sim([[0, 0], [0, 0]], [[0, 0], [0, 0]])
    out = bi.compute({"status_quo": zero, "agentflow_v1": zero, "agentflow_v2": zero}, np.zeros((2, 2)), CLUSTER)
    v2 = out["calculations"]["vs_status_quo"]["agentflow_v2"]
    assert out["calculations"]["policies"]["status_quo"]["customer"]["demand_fill_rate_pct"] is None
    assert v2["economics"]["peer_cost_per_estimated_transaction_protected_bdt"] is None
    assert v2["economics"]["peer_cost_per_bdt_1000_protected"] is None
    assert v2["distributor"]["break_even_fee_per_trip_bdt"] is None
    assert out["calculations"]["policies"]["agentflow_v2"]["operations"]["average_cost_per_peer_transfer_bdt"] is None
    json.dumps(out, allow_nan=False)  # no NaN/inf anywhere


def test_ticket_estimate_handles_zero_counts_and_never_exceeds_counted_transactions():
    amount = np.array([[10_000.0, 500.0, 0.0]])
    counts = np.array([[4, 0, 0]])
    ticket, fallback = bi.ticket_matrix(amount, counts, np.array([[2_000.0, 1_300.0, 1_700.0]]))
    assert ticket.tolist() == [[2_500.0, 1_300.0, 1_700.0]] and fallback.tolist() == [[False, True, True]]
    assert bi.estimated_failed_transactions(amount, ticket) <= counts.sum() + 500 / 1_300 + 1e-9
    assert bi.estimated_failed_transactions(np.array([[-5.0, 0, 0]]), ticket) == 0.0  # negative unmet ignored
    with pytest.raises(ValueError):
        bi.ticket_matrix(amount, counts, np.array([[0.0, 1.0, 1.0]]))


# ------------------------------------------------------------------ assumptions
def test_assumption_validation_and_env_overrides():
    assert bi.assumptions_from_env({}) == bi.BusinessAssumptions()
    a = bi.assumptions_from_env({"AGENTFLOW_BUSINESS_AGENT_COMMISSION_BPS": "80", "AGENTFLOW_BUSINESS_DISTRIBUTOR_FEE_PER_TRIP_BDT": "1200"})
    assert a.agent_commission_bps == 80 and a.distributor_fee_per_trip_bdt == 1200
    assert bi.assumptions_from_env({"AGENTFLOW_BUSINESS_DISTRIBUTOR_FEE_PER_TRIP_BDT": " "}).distributor_fee_per_trip_bdt is None
    for env in ({"AGENTFLOW_BUSINESS_AGENT_COMMISSION_BPS": "fifty"}, {"AGENTFLOW_BUSINESS_AGENT_COMMISSION_BPS": "-1"},
                {"AGENTFLOW_BUSINESS_AGENT_COMMISSION_BPS": "20000"}, {"AGENTFLOW_BUSINESS_DISTRIBUTOR_FEE_PER_TRIP_BDT": "nan"}):
        with pytest.raises(ValueError):
            bi.assumptions_from_env(env)
    for bad in ({"sensitivity_commission_bps": ()}, {"sensitivity_cost_multipliers": (0.0,)}, {"agent_commission_bps": True}):
        with pytest.raises(ValueError):
            bi.BusinessAssumptions(**bad)


def test_reprice_changes_only_assumption_based_figures():
    a = bi.BusinessAssumptions(agent_commission_bps=100)
    r = bi.reprice(BIZ, a)
    assert r["calculations"]["policies"] == BIZ["calculations"]["policies"]  # direct measurements untouched
    v2_old, v2_new = BIZ["calculations"]["vs_status_quo"]["agentflow_v2"], r["calculations"]["vs_status_quo"]["agentflow_v2"]
    assert v2_new["customer"] == v2_old["customer"]
    assert v2_new["agent"]["illustrative_commission_protected_bdt"] == pytest.approx(2 * v2_old["agent"]["illustrative_commission_protected_bdt"], abs=0.02)
    assert r["assumptions"]["agent_commission_bps"] == 100


def test_sensitivity_is_monotone_and_consistent():
    s = BIZ["sensitivity"]["agentflow_v2"]
    grid = s["grid"]
    by = {(g["cost_multiplier"], g["agent_commission_bps"]): g["net_illustrative_value_bdt"] for g in grid}
    rates = sorted({k[1] for k in by})
    mults = sorted({k[0] for k in by})
    assert len(rates) >= 3 and len(mults) >= 2
    for m in mults:
        assert all(by[(m, r1)] < by[(m, r2)] for r1, r2 in zip(rates, rates[1:]))
    for r in rates:
        assert all(by[(m1, r)] > by[(m2, r)] for m1, m2 in zip(mults, mults[1:]))
    be = {b["cost_multiplier"]: b["break_even_commission_bps"] for b in s["break_even_commission_bps_by_cost_multiplier"]}
    assert be[1.0] == pytest.approx(BIZ["calculations"]["vs_status_quo"]["agentflow_v2"]["economics"]["peer_transfers_only"]["break_even_commission_bps"])
    assert be[0.5] == pytest.approx(be[1.0] / 2)


# ------------------------------------------------------------------ methodology and labels
def test_direct_vs_estimated_methodology_is_explicit():
    m = BIZ["methodology"]
    assert any("transaction" in x for x in m["estimated"]) and not any("transaction" in x and "count" not in x for x in m["direct"])
    assert "requested cash-out transaction counts" in m["direct"]
    assert BIZ["metric_definitions"]["estimated_failed_transactions"].startswith("ESTIMATE")
    assert BIZ["metric_definitions"]["illustrative_commission_protected_bdt"].startswith("ASSUMPTION-BASED")
    assert 0 <= m["fallback_ticket_share_of_status_quo_unmet_pct"] < 5
    sq = BIZ["calculations"]["policies"]["status_quo"]["customer"]
    assert sq["estimated_failed_transactions"] < sq["requested_cash_out_transactions"]
    assert isinstance(sq["requested_cash_out_transactions"], int) and isinstance(sq["estimated_failed_transactions"], float)


def test_every_financial_block_is_labelled_and_no_roi_is_claimed():
    assert BIZ["label"] == LABEL and BIZ["synthetic_data"] is True and BIZ["simulated_estimate"] is True
    assert BIZ["version"] == bi.VERSION and BIZ["assumptions"]["label"] == LABEL
    for k, v in BIZ["calculations"]["vs_status_quo"].items():
        assert v["agent"]["label"] == LABEL and v["economics"]["label"] == LABEL
        assert v["economics"]["roi"] is None and "No ROI" in v["economics"]["roi_note"]
    for s in BIZ["sensitivity"].values():
        assert s["label"] == LABEL
    assert "not upay's or any provider's" in BIZ["assumptions"]["agent_commission_note"]


def test_business_layer_is_deterministic(small_data, small_features, small_bundle):
    f = small_features
    usable = f["out_same_window_avg7"].notna() & f["out_rolling_mean_168h"].notna()
    preds = small_bundle.predict(f.loc[usable])
    hist = f[(f["timestamp"] < config.TEST_START) & f["hour"].between(8, 21)].groupby("agent_id")["liquidity_shortage"].mean()
    a = bi.BusinessAssumptions()
    r1 = bi.run(f, small_data.agents, preds, hist, a=a)
    r2 = bi.run(f, small_data.agents, preds, hist, a=a)
    assert r1 == r2
    assert set(r1["calculations"]["policies"]) == {"status_quo", "agentflow_v1", "agentflow_v2", "agentflow_v2_logistics_ranking_experiment"}


# ------------------------------------------------------------------ evidence preservation
def test_reuses_the_same_simulations_as_impact_json():
    rec = BIZ["reconciliation_with_impact_json"]
    assert rec and all(v["match"] for v in rec.values())
    assert bi.reconcile(BIZ, IMPACT) == rec


def test_phase1_evidence_preserved():
    p = IMPACT["policies"]["agentflow_v2"]
    assert (p["shortage_events"], p["interventions"]) == (1223, 345)
    assert round(IMPACT["agentflow_v2_vs_status_quo"]["shortage_events_reduction_pct"], 1) == 39.4
    assert round(IMPACT["agentflow_v2_vs_status_quo"]["unmet_demand_reduction_pct"], 1) == 40.3
    mp = json.loads((config.ARTIFACTS_DIR / "morning_plan_evidence.json").read_text())
    assert round(mp["combined_unmet_reduction_pct"]["median"], 1) == 20.6
    assert "business" not in json.dumps(IMPACT).lower()  # business layer lives in its own artifact


def test_phase2_logistics_evidence_preserved():
    p2 = IMPACT["phase2_logistics"]
    assert p2["version"] == "phase2-logistics-2"
    # values unchanged since phase2-logistics-1; only the keys were made explicit
    assert p2["policies"]["agentflow_v2"]["peer_transfer_logistics_cost_bdt"] == 209_481.66
    assert p2["policies"]["agentflow_v2_logistics_ranking_experiment"]["peer_transfer_logistics_cost_bdt"] == 208_611.9
    assert p2["v2_ranking_change"]["transfer_legs_changed"] == 13
    assert p2["v2_ranking_change"]["logistics_proxy_ranking"]["shortage_events"] == 1229


# ------------------------------------------------------------------ API and frontend wording
@pytest.fixture(scope="module")
def client():
    warnings.filterwarnings("ignore", category=DeprecationWarning)
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as c:
        yield c


def test_api_contract(client):
    r = client.get("/api/business-impact")
    assert r.status_code == 200
    j = r.json()
    assert j["synthetic_data"] is True and j["simulated_estimate"] is True and j["label"] == LABEL
    for key in ("assumptions", "metric_definitions", "calculations", "sensitivity", "limitations", "methodology"):
        assert j[key]
    assert {"policies", "vs_status_quo"} <= set(j["calculations"])
    assert j["calculations"]["vs_status_quo"]["agentflow_v2"]["customer"] == BIZ["calculations"]["vs_status_quo"]["agentflow_v2"]["customer"]
    assert client.post("/api/business-impact").status_code == 405  # read-only


def test_frontend_wording_is_claim_safe():
    card = (ROOT / "apps/web/src/components/BusinessImpact.tsx").read_text()
    assert LABEL in card and "Business Impact — Synthetic Simulation" in card
    assert "No ROI is claimed" in card and "illustrative assumption, not upay&apos;s or any provider&apos;s rate" in card
    assert "Same liquidity. Placed ahead of demand." in card
    assert "BusinessImpactCard" in (ROOT / "apps/web/src/app/impact/page.tsx").read_text()
    texts = [card.lower(), json.dumps(BIZ).lower(), (ROOT / "ml/agentflow/business_impact.py").read_text().lower()]
    for t in texts:
        for phrase in FORBIDDEN:
            assert phrase not in t, phrase
