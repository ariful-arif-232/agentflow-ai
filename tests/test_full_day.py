"""Phase 2E full-day ML: targets, leakage, baselines, models, conservation and the confirmatory bar."""
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from agentflow import dual_world as dw, full_day as fd, ml_attribution as ma


def test_preregistered_constants_and_seed_sets():
    assert fd.DEV_SEEDS == (2026, 2027, 2028, 2029, 2030)
    assert fd.CONFIRMATORY_SEEDS == (2031, 2032, 2033, 2034, 2035)
    assert not set(fd.DEV_SEEDS) & set(fd.CONFIRMATORY_SEEDS)
    assert (fd.INFO_CUTOFF_HOUR, fd.ALLOCATION_HOUR, fd.OPERATING_HOURS) == (7, 8, tuple(range(8, 24)))
    assert fd.COVERAGE_RANGE == (0.85, 0.95) and fd.COMPARATOR == "seasonal_requirement_7d"
    assert len(fd.FEATURES) == 30 and len(set(fd.FEATURES)) == 30
    assert set(fd.MODEL_SPECS) == {"full_day_cash_requirement_p50", "full_day_cash_requirement_p90",
                                   "full_day_efloat_requirement_p50", "full_day_efloat_requirement_p90"}
    assert [s["quantile"] for s in fd.MODEL_SPECS.values()] == [None, 0.9, None, 0.9]
    doc = (Path(__file__).resolve().parents[1] / "docs" / "FULL_DAY_ML_PROTOCOL.md").read_text()
    for token in ("2031, 2032, 2033, 2034, 2035", "2026, 2027, 2028, 2029, 2030", "[85%, 95%]", "4 of 5"):
        assert token in doc


def test_features_contain_no_labels_or_future_information():
    banned = ("future", "unmet", "served", "flow_event", "anomaly", "requirement")
    assert not any(b in f for f in fd.FEATURES for b in banned)


def _hourly(n_days=2, agents=("AG-0001", "AG-0002"), seed=0):
    ts = pd.date_range("2026-08-01", periods=24 * n_days, freq="h")
    rng = np.random.default_rng(seed)
    rows = []
    for a in agents:
        rows.append(pd.DataFrame({"timestamp": ts, "agent_id": a,
                                  "requested_cash_out": rng.integers(0, 20, len(ts)) * 100.0,
                                  "requested_cash_in": rng.integers(0, 20, len(ts)) * 100.0}))
    return pd.concat(rows, ignore_index=True)


def test_full_day_targets_use_only_hours_08_to_23():
    h = _hourly(1, agents=("AG-0001",))
    h.loc[:, ["requested_cash_out", "requested_cash_in"]] = 0.0
    hr = h["timestamp"].dt.hour
    h.loc[hr == 3, "requested_cash_out"] = 99_999.0  # night: outside the operating window
    h.loc[hr == 9, "requested_cash_out"] = 10_000.0
    h.loc[hr == 10, "requested_cash_in"] = 4_000.0
    h.loc[hr == 12, "requested_cash_out"] = 3_000.0
    h.loc[hr == 18, "requested_cash_in"] = 30_000.0
    a = fd.daily_arrays(h, ["AG-0001"])
    # cumulative out-in over 08..23: 10k, 6k, 9k, -21k -> cash 10k; in-out peak: 21k
    assert a["cash_req"][0, 0] == 10_000.0 and a["efloat_req"][0, 0] == 21_000.0
    assert a["cash_out"][0, 0] == 13_000.0 and a["cash_in"][0, 0] == 34_000.0


@pytest.fixture(scope="module")
def small_world():
    return dw.generate_world(seed=7, n_agents=24)


@pytest.fixture(scope="module")
def small_daily(small_world):
    return fd.build_daily(small_world.hourly, small_world.agents)


def test_one_row_per_agent_day_after_history(small_world, small_daily):
    d = small_daily
    assert not d.duplicated(["date", "agent_id"]).any()
    n_days = small_world.hourly["timestamp"].dt.normalize().nunique()
    assert len(d) == 24 * (n_days - fd.HISTORY_DAYS)
    assert d["date"].min() == pd.Timestamp(dw.START).normalize() + pd.Timedelta(days=7)
    assert (d[[f for f in fd.FEATURES if f not in ("cash_req_sw_mean", "efloat_req_sw_mean")]].notna().all()).all()


def test_baselines_are_prior_day_quantities(small_world, small_daily):
    ids = sorted(small_world.agents["agent_id"])
    a = fd.daily_arrays(small_world.hourly, ids)
    k = 20
    day = a["dates"][k]
    rows = small_daily[small_daily["date"] == day].sort_values("agent_id")
    assert np.allclose(rows["cash_req_mean7"], a["cash_req"][k - 7:k].mean(axis=0))
    assert np.allclose(rows["efloat_req_mean7"], a["efloat_req"][k - 7:k].mean(axis=0))
    assert np.allclose(rows["prev_cash_req"], a["cash_req"][k - 1])
    assert np.allclose(rows["cash_req_lag7"], a["cash_req"][k - 7])
    assert np.allclose(rows["cash_req_sw_mean"], (a["cash_req"][k - 7] + a["cash_req"][k - 14]) / 2)
    assert np.allclose(rows[fd.TARGETS["cash"]], a["cash_req"][k])


def test_no_future_leakage_after_information_cutoff(small_world, small_daily):
    cut_day = pd.Timestamp("2026-08-10")
    h = small_world.hourly.copy()
    fut = h["timestamp"] >= cut_day + pd.Timedelta(hours=fd.INFO_CUTOFF_HOUR)
    h.loc[fut, ["requested_cash_out", "requested_cash_in"]] = h.loc[fut, ["requested_cash_out", "requested_cash_in"]] * 5 + 777
    pert = fd.build_daily(h, small_world.agents)
    base_rows = small_daily[small_daily["date"] <= cut_day].reset_index(drop=True)
    pert_rows = pert[pert["date"] <= cut_day].reset_index(drop=True)
    pd.testing.assert_frame_equal(base_rows[fd.FEATURES], pert_rows[fd.FEATURES])
    # the target of the cut-off day DOES change (it is the future the model must predict)
    assert not np.allclose(base_rows.loc[base_rows["date"] == cut_day, fd.TARGETS["cash"]],
                           pert_rows.loc[pert_rows["date"] == cut_day, fd.TARGETS["cash"]])


def test_models_ordered_quantiles_and_deterministic(small_daily):
    tr = small_daily[small_daily["date"] < fd.DEV_VALIDATION_START]
    va = small_daily[(small_daily["date"] >= fd.DEV_VALIDATION_START) & (small_daily["date"] < fd.TEST_START)]
    p1 = fd.predict(fd.train(tr, max_iter=30), va)
    p2 = fd.predict(fd.train(tr, max_iter=30), va)
    pd.testing.assert_frame_equal(p1, p2)
    for r in ("cash", "efloat"):
        assert (p1[f"pred_{r}_p50"] >= 0).all() and (p1[f"pred_{r}_p90"] >= p1[f"pred_{r}_p50"]).all()


def test_policies_share_budgets_allocator_and_conserve_exactly(small_world, small_daily):
    va = small_daily[(small_daily["date"] >= fd.DEV_VALIDATION_START) & (small_daily["date"] < fd.TEST_START)]
    tr = small_daily[small_daily["date"] < fd.DEV_VALIDATION_START]
    preds = fd.predict(fd.train(tr, max_iter=30), va)
    days = pd.DatetimeIndex(sorted(va["date"].unique()))[:3]
    sim = fd.simulate_policies(small_world.hourly, small_world.agents, va, preds, days)
    assert all(c["exact"] and c["max_abs_district_diff_bdt"] == 0 for c in sim["conservation"].values())
    ag = small_world.agents.sort_values("agent_id").reset_index(drop=True)
    rows = va[va["date"] == days[0]].sort_values("agent_id")
    ac, ae, _ = ma.allocate(ag, preds.loc[rows.index, "pred_cash_p90"], preds.loc[rows.index, "pred_efloat_p90"], "need")
    assert np.array_equal(sim["plans"][fd.ML_POLICY][0][days[0]], ac)
    bc, be, _ = ma.allocate(ag, rows["cash_req_mean7"], rows["efloat_req_mean7"], "need")
    assert np.array_equal(sim["plans"][fd.COMPARATOR][1][days[0]], be)
    imp = fd.impact_summary(sim)
    assert imp["conserved_all_policies"] and imp["best_simple_policy"] in fd.BASELINES
    total = sim["sims"][fd.ML_POLICY]["cash"] + sim["sims"][fd.ML_POLICY]["efloat"]
    assert np.allclose(total.sum(axis=1), sim["budgets"]["cash"] + sim["budgets"]["efloat"])


def _seed(comb, cash=0.0, ef=0.0, cons=True):
    return {"incremental": {"combined_unmet_reduction_pct": comb, "cash_unmet_reduction_pct": cash,
                            "efloat_unmet_reduction_pct": ef}, "conserved_all_policies": cons}


def test_confirmatory_bar_logic():
    good = {s: _seed(v) for s, v in zip(fd.CONFIRMATORY_SEEDS, (9.0, 7.0, 6.0, 5.0, -2.0))}
    cov = {"cash": 0.89, "efloat": 0.91}
    r = fd.confirmatory_bar(good, cov)
    assert r["passes"] and fd.confirmatory_bar(good, cov) == r
    assert not fd.confirmatory_bar(good, {"cash": 0.84, "efloat": 0.91})["passes"]  # E
    assert not fd.confirmatory_bar({s: _seed(v) for s, v in zip(fd.CONFIRMATORY_SEEDS, (9, 7, 4, 3, 2))}, cov)["passes"]  # B
    assert not fd.confirmatory_bar({s: _seed(v) for s, v in zip(fd.CONFIRMATORY_SEEDS, (9, 7, 6, -1, -2))}, cov)["passes"]  # A
    two = {s: _seed(9.0, ef=-6.0 if i < 2 else 0.0) for i, s in enumerate(fd.CONFIRMATORY_SEEDS)}
    assert not fd.confirmatory_bar(two, cov)["passes"]  # C
    assert not fd.confirmatory_bar({**good, 2031: _seed(9.0, cons=False)}, cov)["passes"]  # D


def test_plausibility_rule():
    def fm(cov_c, cov_e, ml, naive):
        mk = lambda c: {"p90": {"empirical_coverage": c}, "ml_p50": {"mae": ml},  # noqa: E731
                        "baselines": {"yesterday_requirement": {"mae": naive}}}
        return {"cash": mk(cov_c), "efloat": mk(cov_e)}
    assert not fd.plausibility(fm(0.9, 0.9, 10, 12), True)["clearly_broken"]
    assert fd.plausibility(fm(0.6, 0.9, 10, 12), True)["clearly_broken"]
    assert fd.plausibility(fm(0.9, 0.9, 13, 12), True)["clearly_broken"]
    assert fd.plausibility(fm(0.9, 0.9, 10, 12), False)["clearly_broken"]
