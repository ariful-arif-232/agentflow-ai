"""Phase 2D ML attribution: history signals, same allocator/budgets, conservation and the ML-value bar."""
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from agentflow import ml_attribution as ma, prepositioning as pp

DAY = pd.Timestamp("2026-08-20")


def agents_frame(n=8, seed=0):
    rng = np.random.default_rng(seed)
    return pd.DataFrame({"agent_id": [f"AG-{i:04d}" for i in range(1, n + 1)],
                         "district": ["Dhaka" if i % 3 else "Sylhet" for i in range(n)],
                         "target_cash_level": rng.integers(10, 80, n) * 500.0,
                         "target_efloat_level": rng.integers(10, 80, n) * 500.0})


def flows(n_agents=8, days=14, seed=1):
    hours = pd.date_range("2026-08-08", periods=days * 24, freq="h")
    rng = np.random.default_rng(seed)
    return hours, rng.integers(0, 50, (len(hours), n_agents)) * 100.0, rng.integers(0, 50, (len(hours), n_agents)) * 100.0


def test_preregistered_constants_and_names_are_fixed():
    assert ma.SEEDS == (2026, 2027, 2028, 2029, 2030)
    assert ma.SIMPLE_BASELINES == ("history_proportional", "seasonal_requirement_7d")
    assert ma.ML_POLICY == "agentflow_ml_p90"
    assert ma.OPERATIONAL_POLICIES == ("status_quo", "history_proportional", "seasonal_requirement_7d", "agentflow_ml_p90")
    assert ma.HISTORY_DAYS == 7
    assert ma.BAR == {"min_seeds_ml_not_worse": 4, "min_median_incremental_combined_pct": 5.0,
                      "max_side_increase_pct": 5.0, "max_seeds_with_side_increase": 1}
    assert ma.MODES["history_proportional"] == "proportional"
    assert ma.MODES["seasonal_requirement_7d"] == ma.MODES[ma.ML_POLICY] == "need"
    doc = (Path(__file__).resolve().parents[1] / "docs" / "ML_ATTRIBUTION_PROTOCOL.md").read_text()
    assert "2026, 2027, 2028, 2029" in doc and "4 of 5" in doc and "5%" in doc


def test_history_uses_only_prior_complete_operational_days():
    wins = ma.prior_day_windows(DAY)
    decision = DAY + pd.Timedelta(hours=8)
    assert len(wins) == 7
    assert wins[-1] == (decision - pd.Timedelta(days=1), decision)
    assert wins[0][0] == decision - pd.Timedelta(days=7)
    assert all(end <= decision and end - start == pd.Timedelta(hours=24) for start, end in wins)


def test_history_signals_ignore_everything_at_or_after_the_decision():
    hours, ro, ri = flows()
    base = ma.history_signals(ro, ri, hours, DAY)
    fut = np.asarray(hours >= DAY + pd.Timedelta(hours=8))
    ro2, ri2 = ro.copy(), ri.copy()
    ro2[fut] = ro2[fut] * 9 + 12_345
    ri2[fut] = ri2[fut] * 7 + 999
    pert = ma.history_signals(ro2, ri2, hours, DAY)
    for k in base:
        assert np.array_equal(base[k], pert[k])
    # and they do depend on the prior window
    past = np.asarray((hours >= DAY - pd.Timedelta(days=1)) & (hours < DAY + pd.Timedelta(hours=8)))
    ro3 = ro.copy()
    ro3[past] += 5_000
    assert not np.array_equal(ma.history_signals(ro3, ri, hours, DAY)["avg_daily_cash_out"], base["avg_daily_cash_out"])


def test_history_signals_require_complete_windows():
    hours, ro, ri = flows(days=5)
    with pytest.raises(ValueError):
        ma.history_signals(ro, ri, hours, hours[0].normalize() + pd.Timedelta(days=4))


def test_peak_requirements_hand_example():
    out = np.array([[10.0], [0.0], [30.0], [0.0]])
    inn = np.array([[0.0], [25.0], [0.0], [40.0]])
    # cumulative out-in: 10, -15, 15, -25 -> cash peak 15; in-out: -10, 15, -15, 25 -> e-float peak 25
    c, e = ma.peak_requirements(out, inn)
    assert c[0] == 15.0 and e[0] == 25.0


@pytest.mark.parametrize("mode", ["need", "proportional"])
def test_every_policy_uses_same_budgets_and_conserves_exactly(mode):
    a = agents_frame()
    rng = np.random.default_rng(3)
    ac, ae, edges = ma.allocate(a, rng.uniform(0, 9e4, len(a)), rng.uniform(0, 9e4, len(a)), mode)
    assert edges == 0 and (ac >= pp.FLOOR_CASH_BDT).all() and (ae >= pp.FLOOR_EFLOAT_BDT).all()
    for alloc, col in ((ac, "target_cash_level"), (ae, "target_efloat_level")):
        got = pd.Series(alloc).groupby(a["district"].to_numpy()).sum()
        want = a.groupby("district")[col].sum().astype(np.int64)
        assert (got == want).all() and int(alloc.sum()) == int(a[col].sum())


def test_need_mode_is_identical_to_the_phase_2c_allocator():
    a = agents_frame(10, seed=4)
    rng = np.random.default_rng(5)
    c, e = rng.uniform(0, 6e4, 10), rng.uniform(0, 6e4, 10)
    ac, ae, _ = ma.allocate(a, c, e, "need")
    ref, _ = pp.allocate_day(a.assign(pred_net_requirement_p90_6h=c, pred_efloat_requirement_p90_6h=e))
    assert np.array_equal(ac, ref["alloc_cash"].to_numpy()) and np.array_equal(ae, ref["alloc_efloat"].to_numpy())


def test_proportional_mode_is_floor_plus_proportional_share():
    a = pd.DataFrame({"agent_id": ["AG-0001", "AG-0002"], "district": "Dhaka",
                      "target_cash_level": [50_000.0, 50_000.0], "target_efloat_level": [20_000.0, 20_000.0]})
    ac, ae, _ = ma.allocate(a, [1.0, 3.0], [1.0, 1.0], "proportional")
    assert list(ac) == [5_000 + 22_500, 5_000 + 67_500]
    assert list(ae) == [20_000, 20_000]


def test_allocation_is_deterministic():
    a = agents_frame(12, seed=6)
    s = np.random.default_rng(7).uniform(0, 5e4, (2, 12))
    r1, r2 = ma.allocate(a, s[0], s[1], "need"), ma.allocate(a, s[0], s[1], "need")
    assert all(np.array_equal(x, y) for x, y in zip(r1, r2))


def test_best_simple_selection_and_incremental_metrics():
    m = {"history_proportional": {"combined_unmet_bdt": 100.0}, "seasonal_requirement_7d": {"combined_unmet_bdt": 80.0}}
    assert ma.best_simple(m) == "seasonal_requirement_7d"
    m["seasonal_requirement_7d"]["combined_unmet_bdt"] = 100.0
    assert ma.best_simple(m) == "history_proportional"  # tie -> history_proportional
    best = {"combined_unmet_bdt": 200.0, "unmet_cash_out_bdt": 100.0, "unmet_cash_in_bdt": 100.0, "shortage_events_total": 50}
    ml = {"combined_unmet_bdt": 170.0, "unmet_cash_out_bdt": 60.0, "unmet_cash_in_bdt": 110.0, "shortage_events_total": 45}
    inc = ma.incremental(ml, best)
    assert inc == {"combined_unmet_reduction_pct": 15.0, "cash_unmet_reduction_pct": 40.0,
                   "efloat_unmet_reduction_pct": -10.0, "shortage_event_difference": -5}


def _seed(comb, cash=0.0, ef=0.0, cons=True):
    return {"incremental": {"combined_unmet_reduction_pct": comb, "cash_unmet_reduction_pct": cash,
                            "efloat_unmet_reduction_pct": ef}, "conserved_all_policies": cons}


def test_ml_value_bar_is_deterministic_and_matches_the_rule():
    passing = {s: _seed(v) for s, v in zip(ma.SEEDS, (10.0, 8.0, 6.0, 5.0, -1.0))}
    r = ma.ml_value_bar(passing)
    assert r["passes"] and r["seeds_ml_not_worse"] == 4 and r["median_incremental_combined_reduction_pct"] == 6.0
    assert ma.ml_value_bar(passing) == r
    assert not ma.ml_value_bar({s: _seed(v) for s, v in zip(ma.SEEDS, (10.0, 8.0, 4.0, 3.0, 2.0))})["passes"]  # median 4%
    assert not ma.ml_value_bar({s: _seed(v) for s, v in zip(ma.SEEDS, (10.0, 8.0, 6.0, -1.0, -2.0))})["passes"]  # 3 of 5
    two_side = {s: _seed(10.0, cash=-6.0 if i < 2 else 0.0) for i, s in enumerate(ma.SEEDS)}
    assert not ma.ml_value_bar(two_side)["passes"]
    one_side = {s: _seed(10.0, ef=-6.0 if i < 1 else 0.0) for i, s in enumerate(ma.SEEDS)}
    assert ma.ml_value_bar(one_side)["passes"]
    assert not ma.ml_value_bar({**passing, 2026: _seed(10.0, cons=False)})["passes"]


def test_operational_signals_contain_no_labels():
    import inspect
    src = "".join(inspect.getsource(fn) for fn in (ma.history_signals, ma.allocate, ma.prior_day_windows))
    for token in ("future_6h", "unmet_cash", "known_anomaly", "oracle"):
        assert token not in src
