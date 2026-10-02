"""Dual-Liquidity World v2: resource-conserving accounting, service rule and world invariants."""
import numpy as np
import pandas as pd
import pytest
from scipy.optimize import linprog

from agentflow import config, dual_world as dw


def _serve(c, e, o, i):
    so, si, c2, e2 = dw.serve_hour(np.array([c]), np.array([e]), np.array([o]), np.array([i]))
    return float(so[0]), float(si[0]), float(c2[0]), float(e2[0])


# ---------------------------------------------------------------- hand-calculated examples
def test_example_a_both_feasible_via_opposite_flow():
    # cash 10k, e-float 30k, cash-out 20k, cash-in 15k: net cash need 5k <= 10k
    assert _serve(10_000, 30_000, 20_000, 15_000) == (20_000, 15_000, 5_000, 35_000)


def test_example_b_cash_out_dominant():
    # net cash need 20k > cash 5k -> all 10k cash-in served, cash-out limited to 5k + 10k = 15k
    so, si, c, e = _serve(5_000, 50_000, 30_000, 10_000)
    assert (so, si, c, e) == (15_000, 10_000, 0, 55_000)
    assert 30_000 - so == 15_000  # unmet cash-out


def test_example_c_cash_in_dominant():
    # net e-float need 20k > e-float 5k -> all 10k cash-out served, cash-in limited to 5k + 10k = 15k
    so, si, c, e = _serve(40_000, 5_000, 10_000, 30_000)
    assert (so, si, c, e) == (10_000, 15_000, 45_000, 0)
    assert 30_000 - si == 15_000  # unmet cash-in


def test_example_d_ample_resources_no_unmet():
    assert _serve(500_000, 500_000, 80_000, 60_000) == (80_000, 60_000, 480_000, 520_000)


def test_example_e_zero_requested_flow():
    assert _serve(7_000, 3_000, 0, 0) == (0, 0, 7_000, 3_000)
    assert _serve(0, 0, 0, 0) == (0, 0, 0, 0)


def test_example_f_multi_hour_conservation_and_reset():
    # 3 agents x 6 hours; hour index 2 is the 08:00 reset
    hod = np.array([6, 7, 8, 9, 10, 11])
    out = np.array([[9e3, 0, 4e3], [20e3, 1e3, 0], [5e3, 30e3, 2e3], [0, 0, 50e3], [40e3, 2e3, 1e3], [1e3, 1e3, 1e3]])
    inn = np.array([[1e3, 6e3, 0], [0, 15e3, 9e3], [8e3, 0, 2e3], [25e3, 3e3, 0], [0, 40e3, 1e3], [2e3, 2e3, 2e3]])
    tc, te = np.array([10e3, 5e3, 20e3]), np.array([8e3, 12e3, 3e3])
    s = dw.simulate_dual(out, inn, tc, te, hod)
    prev_c, prev_e = tc.copy(), te.copy()
    for t in range(6):
        dc = s["cash"][t] - prev_c
        de = s["efloat"][t] - prev_e
        # per-hour accounting: cash and e-float move by exactly the served flows (+ explicit replenishment)
        assert np.allclose(dc, s["cash_replenishment"][t] + s["served_in"][t] - s["served_out"][t])
        assert np.allclose(de, s["efloat_replenishment"][t] + s["served_out"][t] - s["served_in"][t])
        # served transactions exchange value between the two resources: cash_delta + efloat_delta = 0
        assert np.allclose(dc + de, s["cash_replenishment"][t] + s["efloat_replenishment"][t])
        if hod[t] != 8:
            assert np.allclose(s["cash_replenishment"][t], 0) and np.allclose(s["efloat_replenishment"][t], 0)
        prev_c, prev_e = s["cash"][t], s["efloat"][t]
    assert (s["cash"] >= 0).all() and (s["efloat"] >= 0).all()
    assert np.allclose(s["served_out"] + s["unmet_out"], out)
    assert np.allclose(s["served_in"] + s["unmet_in"], inn)
    # after the reset hour the balances restart from the targets
    assert np.allclose(s["cash"][2], tc + s["served_in"][2] - s["served_out"][2])
    # whole sequence: total working capital changes only through replenishment
    total_change = (s["cash"][-1] + s["efloat"][-1]) - (tc + te)
    assert np.allclose(total_change, s["cash_replenishment"].sum(0) + s["efloat_replenishment"].sum(0))


# ---------------------------------------------------------------- optimality / feasibility
def test_service_rule_maximises_served_value_against_lp():
    rng = np.random.default_rng(0)
    for _ in range(300):
        c, e, o, i = rng.choice([0, 1, 2, 5, 10, 20, 40, 80], 4) * 1000 + rng.integers(0, 1000, 4)
        so, si, c2, e2 = _serve(c, e, o, i)
        # feasibility
        assert -1e-9 <= so <= o + 1e-9 and -1e-9 <= si <= i + 1e-9
        assert c2 >= -1e-9 and e2 >= -1e-9
        # LP: maximise so + si  s.t.  so - si <= c,  si - so <= e,  0 <= so <= o, 0 <= si <= i
        lp = linprog([-1, -1], A_ub=[[1, -1], [-1, 1]], b_ub=[c, e], bounds=[(0, o), (0, i)], method="highs")
        assert lp.status == 0
        assert so + si == pytest.approx(-lp.fun, abs=1e-6)


def test_dominant_cases_are_mutually_exclusive():
    rng = np.random.default_rng(1)
    c, e, o, i = (rng.uniform(0, 1e5, 10_000) for _ in range(4))
    out_dom = (o - i) > c
    in_dom = (i - o) > e
    assert not (out_dom & in_dom).any()


# ---------------------------------------------------------------- small world invariants
@pytest.fixture(scope="module")
def small_world():
    return dw.generate_world(seed=7, n_agents=24)


def test_world_is_reproducible(small_world):
    again = dw.generate_world(seed=7, n_agents=24)
    pd.testing.assert_frame_equal(small_world.hourly, again.hourly)
    pd.testing.assert_frame_equal(small_world.agents, again.agents)


def test_world_requested_equals_served_plus_unmet_and_nonnegative(small_world):
    h = small_world.hourly
    for side in ("cash_out", "cash_in"):
        assert np.allclose(h[f"served_{side}"] + h[f"unmet_{side}"], h[f"requested_{side}"])
        assert (h[f"served_{side}"] >= -1e-9).all() and (h[f"unmet_{side}"] >= -1e-9).all()
        assert (h[f"served_{side}"] <= h[f"requested_{side}"] + 1e-9).all()
    assert (h["cash_balance"] >= -1e-9).all() and (h["efloat_balance"] >= -1e-9).all()
    # feature-pipeline aliases are the REQUESTED flows
    assert h["cash_out_amount"].equals(h["requested_cash_out"]) and h["cash_in_amount"].equals(h["requested_cash_in"])


def test_world_conserves_agent_working_capital(small_world):
    h = small_world.hourly.sort_values(["agent_id", "timestamp"])
    a = small_world.agents.set_index("agent_id")
    g = h.groupby("agent_id")
    prev_c = g["cash_balance"].shift(1).fillna(h["agent_id"].map(a["target_cash_level"]))
    prev_e = g["efloat_balance"].shift(1).fillna(h["agent_id"].map(a["target_efloat_level"]))
    dc, de = h["cash_balance"] - prev_c, h["efloat_balance"] - prev_e
    assert np.allclose(dc, h["cash_replenishment"] + h["served_cash_in"] - h["served_cash_out"])
    assert np.allclose(de, h["efloat_replenishment"] + h["served_cash_out"] - h["served_cash_in"])
    no_reset = h["hour"] != dw.OPENING_HOUR
    assert np.allclose((dc + de)[no_reset], 0.0)  # transactions never create or destroy value
    assert np.allclose(h.loc[no_reset, ["cash_replenishment", "efloat_replenishment"]], 0.0)


def test_world_labels_and_event_tags(small_world):
    h = small_world.hourly
    assert (h["cash_shortage_event"] == (h["unmet_cash_out"] > 0)).all()
    assert (h["efloat_shortage_event"] == (h["unmet_cash_in"] > 0)).all()
    assert (h["dual_shortage_event"] == ((h["unmet_cash_out"] > 0) & (h["unmet_cash_in"] > 0))).all()
    # legitimate flow events and behavioural anomalies are labelled separately
    assert set(h["flow_event"].unique()) <= {"", "cash_in_surge", "cash_out_surge", "haat_trader_deposits"}
    assert h["known_anomaly_label"].sum() > 0


def test_provisioning_rule_is_the_preregistered_symmetric_rule(small_world):
    a = small_world.agents
    lo, hi = dw.ASSUMPTIONS["provisioning"]["fraction_range"]
    for col in ("cash_provisioning_fraction", "efloat_provisioning_fraction"):
        assert a[col].between(lo, hi).all()
    exp_cash = np.round(a["base_daily_cash_out"] * a["cash_provisioning_fraction"] / 500) * 500
    exp_ef = np.round(a["expected_daily_cash_in"] * a["efloat_provisioning_fraction"] / 500) * 500
    assert np.allclose(a["target_cash_level"], exp_cash, atol=500)
    assert np.allclose(a["target_efloat_level"], exp_ef, atol=500)


def test_dual_world_uses_separate_paths():
    for new, legacy in ((dw.DATA_DIR, config.DATA_DIR), (dw.MODELS_DIR, config.MODELS_DIR),
                        (dw.ARTIFACTS_DIR, config.ARTIFACTS_DIR)):
        assert new != legacy
    assert dw.DATASET_PATH != config.DATASET_PATH


# ---------------------------------------------------------------- symmetric pressure matrix
def test_resource_status_and_state_matrix():
    st = dw.resource_status([0, 50, 100, 200], [80, 80, 80, 80], [150, 150, 150, 150])
    assert list(st) == ["PRESSURE", "PRESSURE", "WATCH", "COVERED"]
    cash = ["PRESSURE", "PRESSURE", "COVERED", "WATCH", "COVERED", "COVERED"]
    ef = ["PRESSURE", "COVERED", "PRESSURE", "COVERED", "WATCH", "COVERED"]
    assert list(dw.liquidity_state_matrix(cash, ef)) == [
        "DUAL_PRESSURE", "CASH_PRESSURE", "EFLOAT_PRESSURE", "WATCH", "WATCH", "HEALTHY"]
    # symmetric: swapping resources swaps the one-sided states only
    swapped = dw.liquidity_state_matrix(ef, cash)
    assert list(swapped) == ["DUAL_PRESSURE", "EFLOAT_PRESSURE", "CASH_PRESSURE", "WATCH", "WATCH", "HEALTHY"]


def test_same_hour_dual_shortage_is_structurally_impossible(small_world):
    # Net settlement: a cash-out-dominant hour serves all cash-in and vice versa, so one agent can
    # never be short of both resources in the same hour (a property of the rule, not of tuning).
    assert small_world.hourly["dual_shortage_event"].sum() == 0
    rng = np.random.default_rng(3)
    c, e, o, i = (rng.uniform(0, 1e5, 50_000) for _ in range(4))
    so, si, _, _ = dw.serve_hour(c, e, o, i)
    assert not ((so < o - 1e-9) & (si < i - 1e-9)).any()


def test_dual_world_evaluation_smoke(small_world, tmp_path):
    from agentflow import dual_world_eval as ev
    arts = ev.run(small_world, max_iter=25, model_path=tmp_path / "m.joblib")
    assert set(arts) == {"world_summary.json", "forecast_metrics.json", "status_quo_impact.json", "training_metadata.json"}
    fm, sq = arts["forecast_metrics.json"], arts["status_quo_impact.json"]
    for art in arts.values():
        assert art["label"] == ev.LABEL and art["world_version"] == dw.WORLD_VERSION
    b = fm["boundaries"]
    # validation strictly inside training, test after the purge; nothing selected on validation
    assert b["validation_fit_end"] < b["validation"][0] < b["validation"][1] < b["test"][0]
    assert fm["validation"]["used_for_selection"] is False
    for k in ("cash_requirement", "efloat_requirement"):
        e = fm["held_out"][k]
        assert set(e["baselines"]) == {"naive_yesterday", "seasonal_avg_7d"}
        assert 0.0 <= e["quantile_p90"]["empirical_coverage"] <= 1.0
        assert e["quantile_p90"]["mean_band_width"] >= 0.0
    s = sq["held_out_service"]
    for side, fill in (("cash_side", "cash_out_fill_rate"), ("efloat_side", "cash_in_fill_rate")):
        assert 0.0 <= s[side][fill] <= 1.0
    n = s["network"]
    assert n["total_served_bdt"] <= n["total_requested_bdt"]
    assert n["dual_shortage_agent_hours"] == 0
    assert sum(sq["held_out_decision_time_pressure"]["liquidity_state_share"].values()) == pytest.approx(1.0, abs=1e-3)
    from agentflow import forecast
    bundle = forecast.ForecastBundle.load(tmp_path / "m.joblib")
    assert bundle.has_efloat


def test_dual_predictions_are_ordered(small_world, tmp_path):
    from agentflow import dual_world_eval as ev, features, forecast
    f = ev.build(small_world)
    train, test = features.time_split(f)
    p = forecast.train(train, max_iter=25).predict(test)
    for lo, hi in (("pred_net_requirement_6h", "pred_net_requirement_p90_6h"),
                   ("pred_efloat_requirement_6h", "pred_efloat_requirement_p90_6h")):
        assert (p[lo] >= 0).all() and (p[hi] >= p[lo]).all()


def test_production_serving_path_never_reads_the_dual_world():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    files = list((root / "apps" / "api").rglob("*.py")) + [root / "ml" / "agentflow" / "engine.py",
                                                           root / "Dockerfile"]
    for fp in files:
        text = fp.read_text()
        for token in ("dual_world", "data_dual", "models_dual", "artifacts_dual"):
            assert token not in text, f"{fp} references {token}"
