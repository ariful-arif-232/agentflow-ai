"""Synthetic data generation, privacy, split and leakage tests."""
import re

import numpy as np
import pandas as pd

from agentflow import config, data_gen, features


def test_generation_is_reproducible():
    a = data_gen.generate(seed=11, n_agents=10, n_days=10)
    b = data_gen.generate(seed=11, n_agents=10, n_days=10)
    pd.testing.assert_frame_equal(a.hourly, b.hourly)
    pd.testing.assert_frame_equal(a.agents, b.agents)


def test_different_seed_changes_data():
    a = data_gen.generate(seed=11, n_agents=10, n_days=10)
    b = data_gen.generate(seed=12, n_agents=10, n_days=10)
    assert not a.hourly["cash_out_amount"].equals(b.hourly["cash_out_amount"])


def test_no_real_pii_columns_or_values(small_data):
    pii_like = {"name", "phone", "msisdn", "nid", "email", "address", "customer_id", "account_number"}
    cols = set(small_data.hourly.columns) | set(small_data.agents.columns)
    assert not any(any(p in c.lower() for p in pii_like) for c in cols)
    assert small_data.agents["agent_id"].str.fullmatch(r"AG-\d{4}").all()
    # no phone-number-like strings anywhere in object columns
    phone = re.compile(r"(?:\+?880|01[3-9])\d{8}")
    for df in (small_data.agents, small_data.hourly):
        for c in df.select_dtypes(include="object").columns:
            assert not df[c].astype(str).str.contains(phone).any()


def test_dataset_shape_and_sanity(small_data):
    h = small_data.hourly
    assert len(h) == 24 * config.N_DAYS * 24
    assert (h["cash_balance"] >= 0).all()
    assert (h["unmet_cash_out"] >= 0).all()
    assert np.allclose(h["cash_out_served"] + h["unmet_cash_out"], h["cash_out_amount"])
    assert h["known_anomaly_label"].sum() > 0
    assert h["liquidity_shortage"].sum() > 0


def test_injected_patterns_present(small_data):
    h = small_data.hourly.merge(small_data.agents, on="agent_id")
    by_hour = h.groupby("hour")["cash_out_amount"].mean()
    assert by_hour.loc[10:19].mean() > 5 * by_hour.loc[0:5].mean()  # daily cycle
    sal = h.groupby("is_salary_period")["cash_out_amount"].mean()
    assert sal[True] > sal[False] * 1.1  # salary-period uplift
    fri = h[h["day_of_week"] == 4]["cash_out_amount"].mean()
    thu = h[h["day_of_week"] == 3]["cash_out_amount"].mean()
    assert thu > fri  # weekend dip


def test_time_split_is_purged_and_ordered(small_features):
    train, test = features.time_split(small_features)
    assert train["timestamp"].max() < test["timestamp"].min()
    # every training target window ends strictly before the test period
    assert (train["timestamp"] + pd.Timedelta(hours=config.HORIZON_H)).max() < config.TEST_START
    assert test["timestamp"].min() >= config.TEST_START
    assert 0.12 < len(test) / (len(train) + len(test)) < 0.25


def test_targets_are_correct_future_sums(small_features):
    f = small_features
    one = f[f["agent_id"] == f["agent_id"].iloc[0]].reset_index(drop=True)
    i = 500
    expected = one.loc[i + 1:i + 6, "cash_out_amount"].sum()
    assert one.loc[i, "future_6h_cash_demand"] == expected
    net = (one.loc[i + 1:i + 6, "cash_out_amount"] - one.loc[i + 1:i + 6, "cash_in_amount"]).cumsum()
    assert one.loc[i, "future_6h_net_cash_demand"] == max(0.0, net.max())


def test_no_future_leakage_in_features(small_data):
    """Perturbing the future must not change any feature at or before the cut-off."""
    h = small_data.hourly.copy()
    cut = pd.Timestamp("2026-08-10 12:00")
    base = features.build_features(h, small_data.agents)
    future = h["timestamp"] > cut
    for c in ("cash_out_amount", "cash_in_amount", "transaction_count", "unmet_cash_out"):
        h.loc[future, c] = h.loc[future, c] * 7 + 1234
    pert = features.build_features(h, small_data.agents)
    past = base["timestamp"] <= cut
    a = base.loc[past, features.FORECAST_FEATURES].reset_index(drop=True)
    b = pert.loc[past, features.FORECAST_FEATURES].reset_index(drop=True)
    pd.testing.assert_frame_equal(a, b)
    # sanity: targets near the cut-off *do* change (they look into the future)
    near = base["timestamp"] == cut
    assert not np.allclose(base.loc[near, "future_6h_cash_demand"], pert.loc[near, "future_6h_cash_demand"])
