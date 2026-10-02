"""Phase 2F cautious non-ML attribution: seeds, history quantiles, frozen ML, allocator, conservation, bar."""
import hashlib
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from agentflow import dual_world as dw, full_day as fd, ml_attribution as ma, quantile_attribution as qa

ROOT = Path(__file__).resolve().parents[1]


def test_seed_sets_fixed_and_disjoint():
    assert qa.AUDIT_SEEDS == (2036, 2037, 2038, 2039, 2040)
    assert set(qa.PRIOR_SEEDS) == set(range(2026, 2036))
    assert not set(qa.AUDIT_SEEDS) & set(qa.PRIOR_SEEDS)
    assert qa.REGRESSION_SEED in fd.CONFIRMATORY_SEEDS and qa.REGRESSION_SEED not in qa.AUDIT_SEEDS
    doc = (ROOT / "docs" / "QUANTILE_ATTRIBUTION_PROTOCOL.md").read_text()
    assert "2036, 2037, 2038, 2039, 2040" in doc and "x₍₅₎ + 0.4 × (x₍₆₎ − x₍₅₎)" in doc


def test_policy_names_and_bar_are_preregistered():
    assert qa.POLICIES == ("status_quo", "seasonal_requirement_mean7", "seasonal_requirement_q90_7d",
                           "seasonal_requirement_max7", "frozen_full_day_ml_p90", "yesterday_requirement")
    assert qa.CAUTIOUS == ("seasonal_requirement_q90_7d", "seasonal_requirement_max7")
    assert qa.BAR == {"min_seeds_ml_le_q90": 4, "min_seeds_ml_le_max7": 4, "min_median_incremental_pct": 5.0,
                      "max_side_worse_pct": 5.0, "max_seeds_side_worse": 1}
    assert qa.QUANTILE == 0.90 and qa.HISTORY_DAYS == 7


def test_frozen_ml_path_is_byte_identical_to_spec_commit():
    for path, digest in qa.FROZEN_SHA256.items():
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == digest, path
    assert qa.FROZEN_SPEC_COMMIT.startswith("3128176")
    assert len(fd.FEATURES) == 30 and [s["quantile"] for s in fd.MODEL_SPECS.values()] == [None, 0.9, None, 0.9]


def test_q90_exact_formula_and_numpy_equivalence():
    x = np.array([60.0, 0.0, 30.0, 10.0, 50.0, 20.0, 40.0])  # sorted 0..60 step 10 -> h = 5.4 -> 54
    assert qa.q90_linear(x) == pytest.approx(54.0)
    rng = np.random.default_rng(0)
    for _ in range(200):
        a = rng.uniform(0, 1e5, (7, 13))
        assert np.allclose(qa.q90_linear(a, axis=0), np.quantile(a, 0.9, axis=0, method="linear"))
    assert qa.q90_linear(np.full(7, 5.0)) == 5.0


def _arrays(n_days=12, n_agents=3, seed=1):
    rng = np.random.default_rng(seed)
    return {"cash_req": rng.uniform(0, 5e4, (n_days, n_agents)), "efloat_req": rng.uniform(0, 5e4, (n_days, n_agents))}


def test_history_signals_use_previous_7_complete_days_only():
    A = _arrays()
    k = 9
    s = qa.history_signals(A, k)
    w = A["cash_req"][k - 7:k]
    assert np.allclose(s["cash"][qa.MEAN7], w.mean(axis=0))
    assert np.allclose(s["cash"][qa.MAX7], w.max(axis=0))
    assert np.allclose(s["cash"][qa.Q90], np.quantile(w, 0.9, axis=0, method="linear"))
    assert np.allclose(s["efloat"][qa.YESTERDAY], A["efloat_req"][k - 1])
    # no future leakage: changing day k and later leaves the signals unchanged
    B = {kk: v.copy() for kk, v in A.items()}
    B["cash_req"][k:] *= 9
    B["efloat_req"][k:] += 1e6
    s2 = qa.history_signals(B, k)
    for r in ("cash", "efloat"):
        for name in (qa.MEAN7, qa.Q90, qa.MAX7, qa.YESTERDAY):
            assert np.array_equal(s[r][name], s2[r][name])
    with pytest.raises(ValueError):
        qa.history_signals(A, 6)


@pytest.fixture(scope="module")
def small_sim():
    world = dw.generate_world(seed=7, n_agents=24)
    daily = fd.build_daily(world.hourly, world.agents)
    tr = daily[daily["date"] < fd.DEV_VALIDATION_START]
    va = daily[(daily["date"] >= fd.DEV_VALIDATION_START) & (daily["date"] < fd.TEST_START)]
    preds = fd.predict(fd.train(tr, max_iter=30), va)
    days = pd.DatetimeIndex(sorted(va["date"].unique()))[:3]
    return world, va, preds, days, qa.simulate(world.hourly, world.agents, va, preds, days)


def test_identical_allocator_and_exact_conservation(small_sim):
    world, va, preds, days, sim = small_sim
    assert all(c["exact"] and c["max_abs_district_diff_bdt"] == 0 for c in sim["conservation"].values())
    ag = world.agents.sort_values("agent_id").reset_index(drop=True)
    A = fd.daily_arrays(world.hourly, list(ag["agent_id"]))
    d = days[1]
    k = int(np.where(A["dates"] == d)[0][0])
    hs = qa.history_signals(A, k)
    rows = va[va["date"] == d].sort_values("agent_id")
    for name, cs, es in ((qa.Q90, hs["cash"][qa.Q90], hs["efloat"][qa.Q90]),
                         (qa.MAX7, hs["cash"][qa.MAX7], hs["efloat"][qa.MAX7]),
                         (qa.ML, preds.loc[rows.index, "pred_cash_p90"], preds.loc[rows.index, "pred_efloat_p90"])):
        ac, ae, _ = ma.allocate(ag, cs, es, "need")
        assert np.array_equal(sim["plans"][name][0][d], ac) and np.array_equal(sim["plans"][name][1][d], ae)
    # mean7 equals the Phase 2E seasonal_requirement_7d signal (the daily table's cash_req_mean7)
    assert np.allclose(hs["cash"][qa.MEAN7], rows["cash_req_mean7"]) and np.allclose(hs["efloat"][qa.MEAN7], rows["efloat_req_mean7"])
    for c in sim["historical_signal_coverage"].values():
        assert all(0.0 <= v <= 1.0 for v in c.values())


def test_simulation_is_deterministic(small_sim):
    world, va, preds, days, sim = small_sim
    sim2 = qa.simulate(world.hourly, world.agents, va, preds, days)
    for name in sim["plans"]:
        for d in days:
            assert np.array_equal(sim["plans"][name][0][d], sim2["plans"][name][0][d])
        assert np.array_equal(sim["sims"][name]["unmet_in"], sim2["sims"][name]["unmet_in"])


def _seed(ml, q90, mx, cash=0.0, ef=0.0, cons=True):
    prim = {qa.ML: {"combined_unmet_bdt": ml}, qa.Q90: {"combined_unmet_bdt": q90}, qa.MAX7: {"combined_unmet_bdt": mx}}
    best = min(q90, mx)
    return {"prim": prim, "conserved_all_policies": cons,
            "incremental": {"combined_unmet_reduction_pct": 100 * (best - ml) / best,
                            "cash_unmet_reduction_pct": cash, "efloat_unmet_reduction_pct": ef}}


def test_best_cautious_selection_and_bar_logic():
    assert qa.best_cautious({qa.Q90: {"combined_unmet_bdt": 10}, qa.MAX7: {"combined_unmet_bdt": 9}}) == qa.MAX7
    assert qa.best_cautious({qa.Q90: {"combined_unmet_bdt": 9}, qa.MAX7: {"combined_unmet_bdt": 9}}) == qa.Q90
    good = {s: _seed(80, 100, 95) for s in qa.AUDIT_SEEDS}
    r = qa.attribution_bar(good)
    assert r["passes"] and qa.attribution_bar(good) == r
    worse_q90 = {**good, 2036: _seed(101, 100, 120), 2037: _seed(101, 100, 120)}
    assert not qa.attribution_bar(worse_q90)["checks"]["A_ml_le_q90_in_4_of_5"]
    worse_max = {**good, 2036: _seed(101, 120, 100), 2037: _seed(101, 120, 100)}
    assert not qa.attribution_bar(worse_max)["checks"]["B_ml_le_max7_in_4_of_5"]
    small = {s: _seed(97, 100, 100) for s in qa.AUDIT_SEEDS}  # 3% everywhere
    assert not qa.attribution_bar(small)["checks"]["C_median_incremental_vs_best_cautious_ge_5pct"]
    side = {s: _seed(80, 100, 95, ef=-6.0 if i < 2 else 0.0) for i, s in enumerate(qa.AUDIT_SEEDS)}
    assert not qa.attribution_bar(side)["checks"]["D_side_worse_gt5pct_in_at_most_1_seed"]
    assert not qa.attribution_bar({**good, 2040: _seed(80, 100, 95, cons=False)})["passes"]


def test_committed_attribution_artifacts_match_preregistration():
    import json
    art = ROOT / "ml" / "artifacts_dual" / "quantile_attribution_multiseed.json"
    if not art.exists():
        pytest.skip("Phase 2F artifacts not generated")
    m = json.loads(art.read_text())
    assert m["assumptions_version"] == "2A.1" and m["audit_seeds"] == list(qa.AUDIT_SEEDS)
    assert list(m["per_seed"]) == [str(s) for s in qa.AUDIT_SEEDS] and m["bar"] == qa.BAR
    assert m["frozen_ml_spec_commit"] == qa.FROZEN_SPEC_COMMIT
    assert m["frozen_ml_regression_check"]["reproduces_phase_2e"] is True
    for r in m["per_seed"].values():
        assert r["conserved_all_policies"] is True
        assert r["best_cautious_non_ml"] == qa.best_cautious(r["prim"])
        best = r["prim"][r["best_cautious_non_ml"]]["combined_unmet_bdt"]
        want = 100 * (best - r["prim"][qa.ML]["combined_unmet_bdt"]) / best
        assert r["incremental"]["combined_unmet_reduction_pct"] == pytest.approx(want, abs=1e-3)
    assert qa.attribution_bar(m["per_seed"])["passes"] == m["success_bar"]["passes"]
