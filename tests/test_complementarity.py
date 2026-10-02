"""Phase 2B-0 complementarity audit: pre-registered constants, pairing rules and conservation."""
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from agentflow import complementarity as cp

TS = pd.Timestamp("2026-08-20 11:00")
LAT, LON = 23.80, 90.40


def agent(aid, cash, ef, c50=0.0, c90=None, e50=0.0, e90=None, district="Dhaka", dlat=0.0, dlon=0.0,
          status="NORMAL", ts=TS):
    return {"agent_id": aid, "timestamp": ts, "district": district,
            "synthetic_latitude": LAT + dlat, "synthetic_longitude": LON + dlon,
            "cash_balance": float(cash), "efloat_balance": float(ef),
            "pred_net_requirement_6h": float(c50), "pred_net_requirement_p90_6h": float(c90 if c90 is not None else c50),
            "pred_efloat_requirement_6h": float(e50), "pred_efloat_requirement_p90_6h": float(e90 if e90 is not None else e50),
            "behaviour_status": status}


def snap(*rows):
    return pd.DataFrame(list(rows))


# A: needs 20k cash (has 10k vs P50 30k), e-float 80k vs reserve max(5k, 1.1*10k)=11k -> surplus 69k
A = dict(aid="AG-0001", cash=10_000, ef=80_000, c50=30_000, c90=40_000, e50=8_000, e90=10_000)
# B: needs 15k e-float (has 5k vs P50 20k), cash 60k vs reserve max(5k, 1.1*20k)=22k -> surplus 38k
B = dict(aid="AG-0002", cash=60_000, ef=5_000, c50=15_000, c90=20_000, e50=20_000, e90=25_000, dlat=0.05)


def test_preregistered_constants_are_fixed():
    assert cp.SEEDS == (2026, 2027, 2028, 2029, 2030)
    assert cp.DECISION_HOURS == (9, 11, 13, 15, 17, 19)
    assert (cp.MAX_DISTANCE_KM, cp.MIN_SWAP_BDT, cp.ROUNDING_BDT) == (15.0, 2_000.0, 500.0)
    assert (cp.RESERVE_FLOOR_BDT, cp.RESERVE_MULTIPLIER) == (5_000.0, 1.10)
    assert cp.BAR == {"min_distinct_agents": 20, "min_viable_pairs": 100,
                      "min_cash_side_share_with_counterparty": 0.10, "min_efloat_side_share_with_counterparty": 0.10}
    assert cp.MIN_WORLDS_PASSING == 4
    doc = (Path(__file__).resolve().parents[1] / "docs" / "DUAL_COMPLEMENTARITY_PROTOCOL.md").read_text()
    assert "2026, 2027, 2028, 2029, 2030" in doc and "4 of 5" in doc


def test_distance_calculation():
    d = cp.haversine_km(LAT, LON, LAT + 0.1, LON)
    assert d == pytest.approx(11.12, abs=0.02)
    assert cp.haversine_km(LAT, LON, LAT, LON) == 0.0


def test_reserves_and_nonnegative_surplus():
    assert list(cp.protected_reserve([0, 1_000, 10_000])) == [5_000, 5_000, 11_000]
    s = cp.safe_surplus([0, 4_000, 20_000, 12_000], [0, 1_000, 10_000, 10_000])
    assert list(s) == [0, 0, 9_000, 1_000]
    assert (cp.safe_surplus(np.random.default_rng(0).uniform(0, 1e5, 1000),
                            np.random.default_rng(1).uniform(0, 1e5, 1000)) >= 0).all()


def test_capacity_min_rounding_and_minimum():
    assert float(cp.swap_capacity(20_000, 15_000, 69_000, 38_000)) == 15_000
    assert float(cp.swap_capacity(9_000, 15_000, 3_000, 38_000)) == 3_000
    assert list(cp.round_down([0, 499, 500, 2_499, 2_500])) == [0, 0, 500, 2_000, 2_500]
    assert list(cp.viable_amount([1_999, 2_000, 2_499, 7_250])) == [0, 2_000, 2_000, 7_000]


def test_pair_direction_and_capacity():
    v = cp.operational_view(snap(agent(**A), agent(**B)))
    assert v.set_index("agent_id").loc["AG-0001", "a_eligible"] and not v.set_index("agent_id").loc["AG-0001", "b_eligible"]
    assert v.set_index("agent_id").loc["AG-0002", "b_eligible"] and not v.set_index("agent_id").loc["AG-0002", "a_eligible"]
    p = cp.candidate_pairs(v)
    assert len(p) == 1 and p.iloc[0]["a"] == "AG-0001" and p.iloc[0]["b"] == "AG-0002"
    # min(A cash need 20k, B e-float need 15k, A e-float surplus 69k, B cash surplus 38k) = 15k
    assert p.iloc[0]["capacity"] == 15_000 and p.iloc[0]["amount"] == 15_000 and p.iloc[0]["viable"]


def test_cash_need_without_efloat_surplus_is_not_a_cash_side_candidate():
    poor = dict(A, ef=9_000)  # e-float below its 11k reserve
    v = cp.operational_view(snap(agent(**poor), agent(**B)))
    assert v["cash_side"].iloc[0] and not v["a_eligible"].iloc[0]
    assert cp.candidate_pairs(v).empty


def test_same_district_and_distance_restriction():
    other_district = dict(B, district="Gazipur")
    assert cp.candidate_pairs(cp.operational_view(snap(agent(**A), agent(**other_district)))).empty
    far = dict(B, dlat=0.2)  # ~22 km
    assert cp.candidate_pairs(cp.operational_view(snap(agent(**A), agent(**far)))).empty


def test_non_normal_behaviour_is_excluded_on_both_sides():
    for which in ("A", "B"):
        rows = (agent(**A, status="WATCH"), agent(**B)) if which == "A" else (agent(**A), agent(**B, status="ANOMALOUS"))
        assert cp.candidate_pairs(cp.operational_view(snap(*rows))).empty


def test_greedy_never_reuses_capacity_and_orders_by_gap():
    # one cash donor B (cash surplus 38k, e-float need 15k) and two cash-pressure agents
    a1 = dict(A, aid="AG-0001", c50=30_000)               # cash need 20k
    a2 = dict(A, aid="AG-0003", c50=40_000, dlat=0.01)    # cash need 30k (larger gap)
    v = cp.operational_view(snap(agent(**a1), agent(**a2), agent(**B)))
    pairs = cp.candidate_pairs(v)
    assert len(pairs) == 2
    alloc = cp.greedy_allocate(v, pairs)
    # B's 15k e-float need can be used only once in total
    assert alloc["amount"].sum() == 15_000
    vi = v.set_index("agent_id")
    for a, g in alloc.groupby("a"):
        assert g["amount"].sum() <= min(vi.loc[a, "cash_need"], vi.loc[a, "efloat_surplus"])
    for b, g in alloc.groupby("b"):
        assert g["amount"].sum() <= min(vi.loc[b, "efloat_need"], vi.loc[b, "cash_surplus"])
    # B (e-float gap 15k) is processed after AG-0003 (cash gap 30k) and before AG-0001 (20k):
    # AG-0003 takes the capacity first
    assert list(alloc["a"]) == ["AG-0003"]


def test_hypothetical_swap_conserves_network_cash_and_efloat():
    cash = {"AG-0001": 10_000.0, "AG-0002": 60_000.0, "AG-0009": 5_000.0}
    ef = {"AG-0001": 80_000.0, "AG-0002": 5_000.0, "AG-0009": 1_000.0}
    c2, e2 = cp.hypothetical_swap(cash, ef, "AG-0001", "AG-0002", 15_000.0)
    assert sum(c2.values()) == sum(cash.values())
    assert sum(e2.values()) == sum(ef.values())
    assert c2["AG-0001"] == 25_000 and e2["AG-0001"] == 65_000  # A gains cash, gives e-float
    assert c2["AG-0002"] == 45_000 and e2["AG-0002"] == 20_000  # B gives cash, gains e-float
    assert cash["AG-0001"] == 10_000  # inputs untouched (nothing is executed)


def _world_like():
    rng = np.random.default_rng(5)
    rows = []
    for t in (TS, TS + pd.Timedelta(hours=2)):
        for i in range(30):
            rows.append(agent(f"AG-{i:04d}", rng.uniform(0, 6e4), rng.uniform(0, 9e4), rng.uniform(0, 5e4), None,
                              rng.uniform(0, 5e4), None, district=("Dhaka" if i % 2 else "Sylhet"),
                              dlat=rng.uniform(-0.05, 0.05), dlon=rng.uniform(-0.05, 0.05), ts=t))
    d = snap(*rows)
    d["pred_net_requirement_p90_6h"] *= 1.3
    d["pred_efloat_requirement_p90_6h"] *= 1.3
    return d


def test_analysis_is_deterministic_and_counts_are_consistent():
    d = _world_like()
    r1, r2 = cp.analyse(d), cp.analyse(d.sample(frac=1.0, random_state=3))
    strip = lambda r: {k: v for k, v in r.items() if not k.startswith("_")}  # noqa: E731
    assert strip(r1) == strip(r2)
    assert r1["cash_rows_with_counterparty"] <= r1["cash_pressure_rows"]
    assert sum(r1["no_counterparty_reasons"]["cash"].values()) == r1["cash_pressure_rows"]
    assert r1["greedy_swappable_bdt"] <= min(r1["total_p50_cash_need_bdt"], r1["total_p50_efloat_need_bdt"])


def test_operational_pairing_ignores_labels_and_future_columns():
    d = _world_like()
    base = cp.analyse(d)
    leak = d.copy()
    rng = np.random.default_rng(9)
    for c in ("future_6h_net_cash_demand", "future_6h_net_efloat_demand", "unmet_cash_out", "unmet_cash_in",
              "unmet_out_next_6h", "unmet_in_next_6h", "known_anomaly_label"):
        leak[c] = rng.uniform(0, 1e6, len(leak))
    strip = lambda r: {k: v for k, v in r.items() if not k.startswith("_")}  # noqa: E731
    assert strip(cp.analyse(leak)) == strip(base)
    assert not any(c.startswith(("future_", "unmet", "known_")) for c in cp.OPERATIONAL_COLUMNS)


def test_bar_check_and_representativeness_rules():
    ok = {"distinct_agents": {"total": 20}, "viable_pairs": 100,
          "cash_side_share_with_counterparty": 0.10, "efloat_side_share_with_counterparty": 0.10}
    assert cp.bar_check(ok)["passes"]
    assert not cp.bar_check({**ok, "viable_pairs": 99})["passes"]
    per = {s: {k: float(i) for k in cp.KEY_METRICS} for i, s in enumerate(cp.SEEDS)}
    per[2026] = {k: 2.0 for k in cp.KEY_METRICS}
    assert cp.representativeness(per)["verdict"] == "typical"
    per[2026] = {k: 99.0 for k in cp.KEY_METRICS}
    assert cp.representativeness(per)["verdict"] == "unusually strong"


def test_committed_audit_artifacts_match_preregistration():
    import json
    art = Path(__file__).resolve().parents[1] / "ml" / "artifacts_dual" / "complementarity_multiseed.json"
    if not art.exists():
        pytest.skip("audit artifacts not generated")
    m = json.loads(art.read_text())
    assert m["assumptions_version"] == "2A.1"
    assert m["constants"]["seeds"] == list(cp.SEEDS) and list(m["per_seed"]) == [str(s) for s in cp.SEEDS]
    assert m["constants"]["bar"] == cp.BAR and m["constants"]["decision_hours"] == list(cp.DECISION_HOURS)
    passing = sum(r["bar"]["passes"] for r in m["per_seed"].values())
    assert m["overall_bar"]["worlds_passing"] == passing
    assert m["overall_bar"]["passes"] == (passing >= cp.MIN_WORLDS_PASSING)
    assert m["per_seed"]["2026"]["phase_2a_artifacts_reproduced"] is True
