"""Phase 2C forecast-guided prepositioning: allocator conservation, determinism, isolation and replay."""
import inspect
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from agentflow import dual_world as dw, prepositioning as pp


def view(n=6, district="Dhaka", seed=0, ids=None):
    rng = np.random.default_rng(seed)
    ids = ids or [f"AG-{i:04d}" for i in range(1, n + 1)]
    return pd.DataFrame({"agent_id": ids, "district": district,
                         "target_cash_level": rng.integers(10, 80, len(ids)) * 500.0,
                         "target_efloat_level": rng.integers(10, 80, len(ids)) * 500.0,
                         "pred_net_requirement_p90_6h": rng.uniform(0, 60_000, len(ids)),
                         "pred_efloat_requirement_p90_6h": rng.uniform(0, 60_000, len(ids))})


def test_preregistered_constants_are_fixed():
    assert pp.SEEDS == (2026, 2027, 2028, 2029, 2030)
    assert (pp.FLOOR_CASH_BDT, pp.FLOOR_EFLOAT_BDT, pp.DECISION_HOUR, pp.FORECAST_ROW_HOUR) == (5_000, 5_000, 8, 7)
    assert pp.BAR == {"max_side_unmet_increase_pct": 2.0, "min_seeds_passing": 4, "min_seeds_reducing_combined": 4,
                      "min_median_combined_reduction_pct": 5.0}
    doc = (Path(__file__).resolve().parents[1] / "docs" / "PREPOSITIONING_PROTOCOL.md").read_text()
    assert "2026, 2027, 2028, 2029" in doc and "4 of 5" in doc and "5%" in doc


def test_largest_remainder_is_exact_and_tie_breaks_by_index():
    assert list(pp.largest_remainder(10, [1, 1, 1])) == [4, 3, 3]
    for total in (0, 1, 7, 12_345, 1_000_001):
        w = np.random.default_rng(total).uniform(0, 5, 17)
        out = pp.largest_remainder(total, w)
        assert out.sum() == total and (out >= 0).all()


def test_allocate_resource_conserves_and_prioritises_largest_need():
    ids = ["AG-0001", "AG-0002", "AG-0003", "AG-0004"]
    sq = np.array([20_000, 20_000, 20_000, 20_000])
    p90 = np.array([10_000, 40_000, 40_000, 2_000])  # AG-0002 / AG-0003 tie on need
    alloc, edge = pp.allocate_resource(ids, 60_000, p90, sq, 5_000)
    assert not edge and alloc.sum() == 60_000 and (alloc >= 5_000).all()
    # floors 20k, remaining 40k; needs 5k, 35k, 35k, 0 -> AG-0002 (tie, lower id) gets 35k, AG-0003 the last 5k
    assert list(alloc) == [5_000, 40_000, 10_000, 5_000]


def test_allocate_resource_leftover_follows_status_quo_proportions():
    ids = ["AG-0001", "AG-0002"]
    alloc, _ = pp.allocate_resource(ids, 100_000, np.array([0.0, 0.0]), np.array([30_000, 70_000]), 5_000)
    assert list(alloc) == [5_000 + 27_000, 5_000 + 63_000]


def test_floor_edge_case_allocates_proportionally():
    ids = ["AG-0001", "AG-0002", "AG-0003"]
    alloc, edge = pp.allocate_resource(ids, 12_000, np.array([9e4, 0, 0]), np.array([1, 1, 2]), 5_000)
    assert edge and alloc.sum() == 12_000 and list(alloc) == [3_000, 3_000, 6_000]


def test_allocate_day_conserves_district_and_network_budgets_and_is_nonnegative():
    v = pd.concat([view(7, "Dhaka", 1), view(5, "Sylhet", 2, ids=[f"AG-01{i:02d}" for i in range(5)])])
    a, edges = pp.allocate_day(v)
    assert edges == 0
    for res, sq in (("alloc_cash", "target_cash_level"), ("alloc_efloat", "target_efloat_level")):
        got = a.groupby("district")[res].sum()
        want = v.groupby("district")[sq].sum().round().astype(np.int64)
        assert (got == want).all()
        assert a[res].sum() == int(v[sq].sum())
        assert (a[res] >= 0).all()


def test_allocation_is_deterministic_and_order_independent():
    v = view(12, seed=4)
    a1, _ = pp.allocate_day(v)
    a2, _ = pp.allocate_day(v.sample(frac=1.0, random_state=1))
    pd.testing.assert_frame_equal(a1, a2)


def test_allocator_ignores_future_labels_and_oracle_columns():
    v = view(10, seed=5)
    base, _ = pp.allocate_day(v)
    leak = v.copy()
    rng = np.random.default_rng(3)
    for c in ("future_6h_net_cash_demand", "future_6h_net_efloat_demand", "unmet_cash_out", "unmet_cash_in"):
        leak[c] = rng.uniform(0, 1e6, len(leak))
    pd.testing.assert_frame_equal(pp.allocate_day(leak)[0], base)
    assert not any(c.startswith(("future_", "unmet")) for c in pp.OPERATIONAL_COLUMNS)
    src = "".join(inspect.getsource(fn) for fn in (pp.allocate_day, pp.allocate_resource, pp.largest_remainder))
    for token in ("future_6h", "unmet_cash", "unmet_next", "oracle"):  # oracles live only in the evaluation script
        assert token not in src.lower()


@pytest.fixture(scope="module")
def small_world():
    return dw.generate_world(seed=7, n_agents=24)


def _mats(world):
    h = world.hourly
    piv = lambda c: h.pivot(index="timestamp", columns="agent_id", values=c).sort_index(axis=1)  # noqa: E731
    return piv("requested_cash_out"), piv("requested_cash_in")


def test_status_quo_replay_uses_same_demand_and_reproduces_world(small_world):
    ro, ri = _mats(small_world)
    a = small_world.agents.sort_values("agent_id")
    tc, te = a["target_cash_level"].to_numpy(), a["target_efloat_level"].to_numpy()
    days = pd.DatetimeIndex(ro.index.normalize().unique())
    sim = pp.replay(ro.to_numpy(), ri.to_numpy(), ro.index, tc, te, {d: tc for d in days}, {d: te for d in days})
    h = small_world.hourly
    rec = lambda c: h.pivot(index="timestamp", columns="agent_id", values=c).sort_index(axis=1).to_numpy()  # noqa: E731
    assert np.allclose(sim["unmet_out"], rec("unmet_cash_out")) and np.allclose(sim["unmet_in"], rec("unmet_cash_in"))
    assert np.allclose(sim["cash"], rec("cash_balance")) and np.allclose(sim["efloat"], rec("efloat_balance"))


def test_replay_conserves_working_capital_between_resets(small_world):
    ro, ri = _mats(small_world)
    a = small_world.agents.sort_values("agent_id")
    v = a.assign(pred_net_requirement_p90_6h=50_000.0, pred_efloat_requirement_p90_6h=10_000.0)
    alloc, _ = pp.allocate_day(v)
    days = pd.DatetimeIndex(ro.index.normalize().unique())
    pc = {d: alloc["alloc_cash"].to_numpy() for d in days}
    pe = {d: alloc["alloc_efloat"].to_numpy() for d in days}
    tc, te = a["target_cash_level"].to_numpy(), a["target_efloat_level"].to_numpy()
    sim = pp.replay(ro.to_numpy(), ri.to_numpy(), ro.index, tc, te, pc, pe)
    total = sim["cash"] + sim["efloat"]
    budget = float(tc.sum() + te.sum())
    # network working capital equals the unchanged daily budget at every hour (transactions only exchange value)
    assert np.allclose(total.sum(axis=1), budget)
    assert (sim["cash"] >= -1e-9).all() and (sim["efloat"] >= -1e-9).all()
    assert np.allclose(sim["served_out"] + sim["unmet_out"], ro.to_numpy())
    assert np.allclose(sim["served_in"] + sim["unmet_in"], ri.to_numpy())


def test_bar_logic():
    sq = {"unmet_cash_out_bdt": 100.0, "unmet_cash_in_bdt": 100.0, "combined_unmet_bdt": 200.0}
    good = {"unmet_cash_out_bdt": 80.0, "unmet_cash_in_bdt": 101.0, "combined_unmet_bdt": 181.0}
    assert pp.seed_bar(sq, good, True)["passes"]
    assert not pp.seed_bar(sq, {**good, "unmet_cash_in_bdt": 103.0, "combined_unmet_bdt": 183.0}, True)["passes"]
    assert not pp.seed_bar(sq, good, False)["passes"]
    per = {s: {"impact": {"combined_unmet_reduction_pct": r}, "bar": {"passes": r > 0}, "conservation": {"exact": True}}
           for s, r in zip(pp.SEEDS, (8.0, 6.0, 5.0, 1.0, -1.0))}
    ob = pp.overall_bar(per)
    assert ob["seeds_passing"] == 4 and ob["median_combined_reduction_pct"] == 5.0 and ob["passes"]
