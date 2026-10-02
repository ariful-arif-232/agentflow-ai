"""Leakage-safe feature engineering and forecast targets.

Convention: a row at timestamp ``t`` describes the *end* of hour ``t``. All features
use observations at hours ``<= t`` only. Targets describe hours ``t+1 .. t+6``.

Targets
-------
future_6h_cash_demand
    Requested cash-out over the next 6 hours (gross customer cash demand).
future_6h_cash_in
    Cash-in over the next 6 hours.
future_6h_net_cash_demand
    *Peak cumulative net cash drain* over the next 6 hours:
    ``max(0, max_k sum_{j=1..k} (cash_out_{t+j} - cash_in_{t+j}))``.
    This is exactly the opening cash an agent needs to serve every cash-out request
    in the window, so it is the quantity the risk engine compares to the cash balance.
future_6h_net_efloat_demand
    The symmetric e-float target (dual-liquidity Phase 1):
    ``max(0, max_k sum_{j=1..k} (cash_in_{t+j} - cash_out_{t+j}))``.
    An agent manages two coupled resources: physical cash supports cash-out, e-float supports
    cash-in, and each transaction shifts value from one side to the other. This is the opening
    e-float needed to accept every *requested* cash-in in the window under the same
    aggregate-flow assumption. It is a requirement, not a record of failed cash-in: the
    synthetic data does not simulate declined cash-in.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import config

H = config.HORIZON_H

CATEGORICAL = {
    "district": None,
    "location_cluster": ["urban_core", "urban_periphery", "rural"],
    "agent_volume_segment": ["low", "medium", "high"],
    "agent_type": ["retail_shop", "grocery", "pharmacy", "market_stall", "transport_hub"],
}

FORECAST_FEATURES = [
    # calendar (known in advance)
    "hour", "day_of_week", "is_weekend", "is_salary_period", "day_of_month",
    "is_market_day", "next_day_is_market_day",
    # static agent attributes (encoded)
    "district_code", "location_cluster_code", "agent_volume_segment_code", "agent_type_code",
    # recent cash-out history
    "out_last_1h", "out_sum_3h", "out_sum_6h", "out_sum_24h", "out_rolling_mean_24h",
    "out_rolling_std_24h", "out_rolling_mean_168h",
    "out_same_window_1d", "out_same_window_7d", "out_same_window_avg7",
    # recent cash-in history
    "in_sum_6h", "in_sum_24h", "in_rolling_mean_168h",
    "in_same_window_1d", "in_same_window_avg7",
    # realised net requirement of the same window on previous days
    "net_req_same_window_1d", "net_req_same_window_7d", "net_req_same_window_avg7",
    # activity / velocity
    "txn_count_3h", "velocity_ratio_3h",
]

TARGETS = ["future_6h_cash_demand", "future_6h_cash_in", "future_6h_net_cash_demand"]

# Dual-liquidity Phase 1: e-float requirement target and its leakage-safe history.
# Kept separate from FORECAST_FEATURES / TARGETS so the validated cash models, the
# train/test split and every legacy V1/V2 result stay exactly as they were.
EFLOAT_TARGET = "future_6h_net_efloat_demand"
EFLOAT_HISTORY_FEATURES = ["efloat_req_same_window_1d", "efloat_req_same_window_7d",
                           "efloat_req_same_window_avg7"]
EFLOAT_FEATURES = FORECAST_FEATURES + EFLOAT_HISTORY_FEATURES


def _encode_static(agents: pd.DataFrame) -> pd.DataFrame:
    a = agents.copy()
    districts = sorted(a["district"].unique())
    for col, cats in CATEGORICAL.items():
        cats = cats or districts
        a[f"{col}_code"] = a[col].map({c: i for i, c in enumerate(cats)}).astype(np.int16)
    return a


def _future_window_sum(g: pd.core.groupby.SeriesGroupBy) -> pd.Series:
    """sum of x[t+1 .. t+H] per agent (NaN where incomplete)."""
    total = None
    for k in range(1, H + 1):
        s = g.shift(-k)
        total = s if total is None else total + s
    return total


def build_features(hourly: pd.DataFrame, agents: pd.DataFrame) -> pd.DataFrame:
    """Return the hourly frame enriched with features and targets (sorted by agent, time)."""
    df = hourly.sort_values(["agent_id", "timestamp"], kind="stable").reset_index(drop=True)
    a = _encode_static(agents)
    keep = ["agent_id", "district", "location_cluster", "agent_type", "agent_volume_segment",
            "synthetic_latitude", "synthetic_longitude", "market_day", "target_cash_level",
            "target_efloat_level",
            "district_code", "location_cluster_code", "agent_volume_segment_code", "agent_type_code"]
    df = df.merge(a[keep], on="agent_id", how="left")

    ts = df["timestamp"]
    df["day_of_month"] = ts.dt.day.astype(np.int8)
    df["is_market_day"] = (df["market_day"] == df["day_of_week"]).astype(np.int8)
    df["next_day_is_market_day"] = (df["market_day"] == (df["day_of_week"] + 1) % 7).astype(np.int8)

    out = df["cash_out_amount"]
    inn = df["cash_in_amount"]
    net = out - inn
    gid = df["agent_id"]
    g_out, g_in, g_net = out.groupby(gid), inn.groupby(gid), net.groupby(gid)

    # ---- targets (future; never used as features) ----
    df["future_6h_cash_demand"] = _future_window_sum(g_out)
    df["future_6h_cash_in"] = _future_window_sum(g_in)
    cum = g_net.cumsum()
    g_cum = cum.groupby(gid)
    peak = None
    for k in range(1, H + 1):
        d = g_cum.shift(-k) - cum
        peak = d if peak is None else np.fmax(peak, d)
    complete = g_cum.shift(-H).notna()
    df["future_6h_net_cash_demand"] = peak.clip(lower=0).where(complete)
    # Symmetric e-float requirement: peak cumulative (cash_in - cash_out) = peak of -(net drain).
    peak_ef = None
    for k in range(1, H + 1):
        d = cum - g_cum.shift(-k)
        peak_ef = d if peak_ef is None else np.fmax(peak_ef, d)
    df[EFLOAT_TARGET] = peak_ef.clip(lower=0).where(complete)
    unmet_future = _future_window_sum(df["unmet_cash_out"].groupby(gid))
    df["shortage_next_6h"] = (unmet_future > 0).astype("float").where(unmet_future.notna())
    df["unmet_next_6h"] = unmet_future

    # ---- history features (only hours <= t) ----
    df["out_last_1h"] = out
    df["out_sum_3h"] = g_out.rolling(3, min_periods=3).sum().reset_index(level=0, drop=True)
    df["out_sum_6h"] = g_out.rolling(6, min_periods=6).sum().reset_index(level=0, drop=True)
    df["out_sum_24h"] = g_out.rolling(24, min_periods=24).sum().reset_index(level=0, drop=True)
    df["out_rolling_mean_24h"] = df["out_sum_24h"] / 24.0
    df["out_rolling_std_24h"] = g_out.rolling(24, min_periods=24).std().reset_index(level=0, drop=True)
    df["out_rolling_mean_168h"] = g_out.rolling(168, min_periods=168).mean().reset_index(level=0, drop=True)
    df["in_sum_6h"] = g_in.rolling(6, min_periods=6).sum().reset_index(level=0, drop=True)
    df["in_sum_24h"] = g_in.rolling(24, min_periods=24).sum().reset_index(level=0, drop=True)
    df["in_rolling_mean_168h"] = g_in.rolling(168, min_periods=168).mean().reset_index(level=0, drop=True)

    # Same forecast window on previous days: target series shifted by >= 24h only
    # (window t-24d+1 .. t-24d+6 ends at t-18 at the latest => fully observed at t).
    for name, target in (("out", "future_6h_cash_demand"), ("in", "future_6h_cash_in"),
                         ("net_req", "future_6h_net_cash_demand"), ("efloat_req", EFLOAT_TARGET)):
        g_t = df[target].groupby(gid)
        lags = [g_t.shift(24 * d) for d in range(1, 8)]
        df[f"{name}_same_window_1d"] = lags[0]
        df[f"{name}_same_window_7d"] = lags[6]
        df[f"{name}_same_window_avg7"] = pd.concat(lags, axis=1).mean(axis=1, skipna=False)
        df[f"{name}_same_window_max7"] = pd.concat(lags, axis=1).max(axis=1, skipna=False)

    cnt = df["transaction_count"].astype(float)
    g_cnt = cnt.groupby(gid)
    df["txn_count_3h"] = g_cnt.rolling(3, min_periods=3).sum().reset_index(level=0, drop=True)
    same_hours_prev = pd.concat([df["txn_count_3h"].groupby(gid).shift(24 * d) for d in range(1, 8)], axis=1)
    df["velocity_ratio_3h"] = df["txn_count_3h"] / (same_hours_prev.mean(axis=1) + 1.0)
    df["transaction_velocity"] = df["txn_count_3h"] / 3.0

    # convenience lag columns named as in the dataset spec
    df["lag_1h"] = g_out.shift(1)
    df["lag_6h"] = g_out.shift(6)
    df["lag_24h"] = g_out.shift(24)
    df["rolling_mean_6h"] = df["out_sum_6h"] / 6.0
    df["rolling_mean_24h"] = df["out_rolling_mean_24h"]
    df["rolling_std_24h"] = df["out_rolling_std_24h"]

    for c in ("is_weekend", "is_salary_period"):
        df[c] = df[c].astype(np.int8)
    return df


def time_split(df: pd.DataFrame, test_start: pd.Timestamp = config.TEST_START):
    """Purged time-based split.

    * train: rows whose 6h target window ends strictly before ``test_start``
      and whose history features are complete (7-day warm-up dropped);
    * test: rows at or after ``test_start`` with a complete target.
    """
    has_hist = df["out_same_window_avg7"].notna() & df["out_rolling_mean_168h"].notna()
    has_target = df[TARGETS].notna().all(axis=1)
    purge_cut = test_start - pd.Timedelta(hours=H)
    train = df[has_hist & has_target & (df["timestamp"] < purge_cut)]
    test = df[has_hist & has_target & (df["timestamp"] >= test_start)]
    return train, test
