"""Serving-default consistency: live V2 uses the proven Phase-1 ranking; published evidence is unchanged."""
import json
import warnings
from dataclasses import replace

import pytest

from agentflow import config, impact, policy_selection, rebalance_v2

A = config.ARTIFACTS_DIR
IMPACT = json.loads((A / "impact.json").read_text())
METRICS = json.loads((A / "metrics.json").read_text())
MORNING = json.loads((A / "morning_plan_evidence.json").read_text())
BIZ = json.loads((A / "business_impact.json").read_text())


def test_serving_default_ranking_is_phase1_simple():
    assert rebalance_v2.SERVING_RANKING_COST_MODEL == "phase1_simple"
    assert rebalance_v2.RebalanceV2Config().ranking_cost_model == "phase1_simple"
    assert rebalance_v2.selected_config().ranking_cost_model == "phase1_simple"
    assert policy_selection.SELECTION_BASE.ranking_cost_model == "phase1_simple"
    # V2 tuned parameters are still the ones selected on the Phase-1 validation folds
    cfg = rebalance_v2.selected_config()
    assert (cfg.target_quantile_weight, cfg.donor_uncertainty_mult, cfg.min_risk_drop) == (1.0, 0.25, 20.0)


def test_logistics_ranking_is_only_used_when_requested_explicitly():
    assert rebalance_v2.EXPERIMENT_RANKING_COST_MODEL == "logistics_proxy"
    cfg = replace(rebalance_v2.selected_config(), ranking_cost_model="logistics_proxy")
    assert cfg.ranking_cost_model == "logistics_proxy"
    src = (config.ML_DIR / "agentflow" / "impact.py").read_text()
    assert "ranking_cost_model=rebalance_v2.EXPERIMENT_RANKING_COST_MODEL" in src


def test_published_phase1_metrics_unchanged():
    cd = METRICS["forecast"]["targets"]["cash_demand"]
    assert round(cd["ml_model"]["mae"]) == 6138 and round(cd["improvement_vs_best_baseline"]["mae_pct"], 1) == 22.2
    ml = METRICS["risk_alerts"]["variants"]["ml_forecast"]
    assert round(ml["precision"], 3) == 0.815 and round(ml["recall"], 3) == 0.417
    assert round(METRICS["anomaly"]["roc_auc"], 3) == 0.981
    p = IMPACT["policies"]
    assert (p["status_quo"]["shortage_events"], p["agentflow_v2"]["shortage_events"]) == (2017, 1223)
    assert p["agentflow_v2"]["unmet_cash_demand_bdt"] == 5_690_940.0
    assert (p["agentflow_v2"]["interventions"], p["agentflow_v2"]["donor_shortage_events_after_transfer"]) == (345, 14)
    assert round(p["agentflow_v2"]["unnecessary_interventions_pct"], 1) == 24.3
    vs = IMPACT["agentflow_v2_vs_status_quo"]
    assert round(vs["shortage_events_reduction_pct"], 1) == 39.4 and round(vs["unmet_demand_reduction_pct"], 1) == 40.3
    assert IMPACT["deployment_decision"]["default_policy"] == "v2"
    assert round(MORNING["combined_unmet_reduction_pct"]["median"], 1) == 20.6


def test_phase2_experiment_is_kept_and_labelled_separately():
    p2 = IMPACT["phase2_logistics"]
    assert p2["serving_v2_ranking_cost_model"] == "phase1_simple"
    assert p2["experiment_ranking_cost_model"] == "logistics_proxy"
    assert p2["experiment_status"].startswith("EXPERIMENTAL — not adopted")
    exp = p2["policies"]["agentflow_v2_logistics_ranking_experiment"]
    assert (exp["shortage_events"], exp["unmet_cash_demand_bdt"], exp["donor_shortage_events_after_transfer"]) == (1229, 5_699_290.0, 15)
    assert round(exp["unnecessary_interventions_pct"], 1) == 24.1
    serving = p2["policies"]["agentflow_v2"]
    assert serving["interventions"] == 345 and serving["peer_transfer_logistics_cost_bdt"] == 209_481.66
    assert "shortage_events" not in serving  # the serving block holds costs only; outcomes live in Phase-1 policies


def test_business_impact_v2_is_the_serving_plan_and_never_mixed():
    pol = BIZ["calculations"]["policies"]
    assert pol["agentflow_v2"]["customer"]["shortage_agent_hours"] == 1223
    assert pol["agentflow_v2"]["operations"]["peer_transfers"] == 345
    assert pol["agentflow_v2_logistics_ranking_experiment"]["customer"]["shortage_agent_hours"] == 1229
    assert "EXPERIMENT" in BIZ["policy_labels"]["agentflow_v2_logistics_ranking_experiment"]
    assert set(BIZ["sensitivity"]) == {"agentflow_v1", "agentflow_v2"}
    assert all(v["match"] for v in BIZ["reconciliation_with_impact_json"].values())
    assert BIZ["version"] == "phase2-business-2"


@pytest.fixture(scope="module")
def client():
    warnings.filterwarnings("ignore", category=DeprecationWarning)
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as c:
        yield c


def test_live_default_plan_restores_phase1_demo_values(client):
    plan = client.get("/api/rebalancing/recommendations").json()
    s = plan["summary"]
    assert plan["policy"] == "v2" and s["config"]["ranking_cost_model"] == "phase1_simple"
    assert (s["n_recommendations"], s["total_recommended_amount"], s["escalated_amount"]) == (14, 472_500.0, 504_000.0)
    rb = next(r for r in plan["recommendations"] if r["id"] == "RB-013")
    assert (rb["source_agent"], rb["destination_agent"], rb["recommended_amount"]) == ("AG-0181", "AG-0171", 38_500.0)
    assert rb["candidate_rank_key"]["ranking_cost_model"] == "phase1_simple"
    assert rb["logistics_cost"]["total_estimated_cost_bdt"] == pytest.approx(903.47)  # still costed with the proxy
    assert client.get("/api/logistics/assumptions").json()["v2_ranking_cost_model"] == "phase1_simple"
    k = client.get("/api/overview").json()["kpis"]
    assert (k["recommended_rebalancing_value"], k["escalated_amount"], k["n_recommendations"]) == (472_500.0, 504_000.0, 14)
