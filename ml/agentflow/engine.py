"""AgentFlow decision engine: joins data, forecasts, anomaly scores and risk into
per-agent snapshots at a decision timestamp ("as-of")."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from . import anomaly, config, data_gen, features, forecast, risk

OPERATING_HOURS = range(8, 22)
DEFAULT_AS_OF = pd.Timestamp("2026-08-31 13:00")
ANOMALY_LOOKBACK_H = 6
SERVING_HISTORY_DAYS = 9  # >= 7-day lags + 6h window + 72h chart before the first decision time


def training_shortage_rate(df: pd.DataFrame) -> pd.Series:
    """Per-agent share of training-period operating hours with a liquidity shortage."""
    train = df[(df["timestamp"] < config.TEST_START) & df["hour"].isin(OPERATING_HOURS)]
    return train.groupby("agent_id")["liquidity_shortage"].mean()


@dataclass
class Engine:
    agents: pd.DataFrame
    feats: pd.DataFrame
    bundle: forecast.ForecastBundle
    detector: anomaly.AnomalyDetector
    hist_rate: pd.Series | None = None
    preds: pd.DataFrame = field(init=False)
    anom: pd.DataFrame = field(init=False)

    def __post_init__(self) -> None:
        f = self.feats
        usable = f["out_same_window_avg7"].notna() & f["out_rolling_mean_168h"].notna()
        self.preds = self.bundle.predict(f.loc[usable])
        af = anomaly.anomaly_features(f)
        self.anom = af
        self.anom["anomaly_score"] = self.detector.score(af)
        self.anom["anomaly_status"] = self.detector.status(self.anom["anomaly_score"].to_numpy())
        if self.hist_rate is None:
            self.hist_rate = training_shortage_rate(f)
        self._ts_index = {ts: idx for ts, idx in f.groupby("timestamp").groups.items()}

    # ------------------------------------------------------------------ loading
    @classmethod
    def load(cls, serving: bool = False) -> "Engine":
        """Load data + models. ``serving=True`` builds features only for the held-out period plus
        the history it needs (8 days), which keeps the API's memory footprint small. Results for
        held-out decision times are identical; training-period statistics come from the full data."""
        data = data_gen.load()
        hourly = data.hourly
        hist_rate = None
        if serving:
            hist_rate = training_shortage_rate(hourly)
            hourly = hourly[hourly["timestamp"] >= config.TEST_START - pd.Timedelta(days=SERVING_HISTORY_DAYS)]
        feats = features.build_features(hourly, data.agents)
        return cls(agents=data.agents, feats=feats, bundle=forecast.ForecastBundle.load(),
                   detector=anomaly.AnomalyDetector.load(), hist_rate=hist_rate)

    @property
    def timestamps(self) -> pd.DatetimeIndex:
        return pd.DatetimeIndex(sorted(self._ts_index))

    def rows_at(self, as_of: pd.Timestamp) -> pd.DataFrame:
        if as_of not in self._ts_index:
            raise KeyError(f"no data at {as_of}")
        return self.feats.loc[self._ts_index[as_of]]

    # ------------------------------------------------------------------ snapshot
    def snapshot(self, as_of: pd.Timestamp = DEFAULT_AS_OF, demand_multiplier: float | pd.Series = 1.0,
                 cash_override: pd.Series | None = None) -> pd.DataFrame:
        """One row per agent with forecast, risk and anomaly fields at ``as_of``.

        demand_multiplier scales forecast requirements (scenario analysis);
        cash_override replaces current cash balances (rebalancing what-if).
        """
        rows = self.rows_at(as_of)
        p = self.preds.reindex(rows.index)
        snap = rows[["agent_id", "timestamp", "district", "location_cluster", "agent_type",
                     "agent_volume_segment", "synthetic_latitude", "synthetic_longitude",
                     "cash_balance", "efloat_balance", "hour", "is_salary_period", "is_market_day",
                     "velocity_ratio_3h", "out_same_window_avg7", "out_rolling_mean_168h",
                     "out_sum_6h", "target_cash_level"]].copy()
        snap = snap.join(p)
        mult = demand_multiplier if np.isscalar(demand_multiplier) else snap["agent_id"].map(demand_multiplier).fillna(1.0).to_numpy()
        for c in ("pred_cash_demand_6h", "pred_net_requirement_6h", "pred_net_requirement_p90_6h"):
            snap[c] = snap[c] * mult
        if cash_override is not None:
            snap["cash_balance"] = snap["agent_id"].map(cash_override).fillna(snap["cash_balance"])
        snap["hist_shortage_rate"] = snap["agent_id"].map(self.hist_rate).fillna(0.0).to_numpy()
        r = risk.compute_risk(snap["cash_balance"], snap["pred_net_requirement_6h"],
                              snap["pred_net_requirement_p90_6h"], snap["velocity_ratio_3h"],
                              snap["hist_shortage_rate"])
        r.index = snap.index
        snap = snap.join(r)
        snap["expected_surplus"] = np.maximum(snap["cash_balance"] - snap["pred_net_requirement_p90_6h"], 0.0)

        # anomaly: worst score in the lookback window ending at as_of
        lb = self.feats["timestamp"].between(as_of - pd.Timedelta(hours=ANOMALY_LOOKBACK_H - 1), as_of)
        win = self.anom.loc[lb, ["anomaly_score"]].join(self.feats.loc[lb, ["agent_id", "timestamp"]])
        worst = win.sort_values("anomaly_score", ascending=False).drop_duplicates("agent_id").set_index("agent_id")
        snap["anomaly_score"] = snap["agent_id"].map(worst["anomaly_score"]).fillna(0.0).round(4)
        snap["anomaly_status"] = self.detector.status(snap["anomaly_score"].to_numpy())
        snap["anomaly_peak_time"] = snap["agent_id"].map(worst["timestamp"])
        snap["review_priority"] = np.where(
            (snap["risk_level"].isin(["HIGH", "CRITICAL"])) & (snap["anomaly_status"] != "NORMAL"), "URGENT_REVIEW",
            np.where(snap["risk_level"].isin(["HIGH", "CRITICAL"]), "REBALANCE_REVIEW",
                     np.where(snap["anomaly_status"] != "NORMAL", "BEHAVIOUR_REVIEW", "NONE")))
        return snap.reset_index(drop=True)

    SERVING_COLUMNS = [
        "agent_id", "timestamp", "district", "location_cluster", "agent_type", "agent_volume_segment",
        "synthetic_latitude", "synthetic_longitude", "cash_balance", "efloat_balance", "hour",
        "is_salary_period", "is_market_day", "velocity_ratio_3h", "out_same_window_avg7",
        "out_rolling_mean_168h", "out_sum_6h", "target_cash_level", "cash_out_amount", "cash_in_amount",
        "unmet_cash_out", "transaction_count", "future_6h_cash_demand", "future_6h_net_cash_demand",
    ]

    def compact(self) -> "Engine":
        """Reduce memory for serving: keep only columns the API reads and use float32 / categories.

        Training, evaluation and the impact simulator use the full-precision engine.
        """
        f = self.feats[self.SERVING_COLUMNS].copy()
        for c in f.columns:
            if f[c].dtype == "float64" and c not in ("synthetic_latitude", "synthetic_longitude"):
                f[c] = f[c].astype("float32")
        for c in ("agent_id", "district", "location_cluster", "agent_type", "agent_volume_segment"):
            f[c] = f[c].astype("category")
        self.feats = f
        self.preds = self.preds.astype("float32")
        a = self.anom
        for c in a.columns:
            if a[c].dtype == "float64":
                a[c] = a[c].astype("float32")
        a["anomaly_status"] = a["anomaly_status"].astype("category")
        import gc
        gc.collect()
        return self

    def anomaly_status_matrix(self) -> pd.DataFrame:
        """timestamp x agent agent-level status (worst score over the trailing lookback window)."""
        sc = self.anom[["anomaly_score"]].join(self.feats[["timestamp", "agent_id"]]).pivot(
            index="timestamp", columns="agent_id", values="anomaly_score")
        sc = sc.rolling(ANOMALY_LOOKBACK_H, min_periods=1).max()
        return pd.DataFrame(self.detector.status(sc.to_numpy()), index=sc.index, columns=sc.columns)

    def run_impact(self, demand_multiplier: float = 1.0) -> dict:
        from . import impact
        return impact.run_impact(self.feats, self.agents, self.preds, self.hist_rate,
                                 self.anomaly_status_matrix(), demand_multiplier)

    def anomaly_drivers(self, agent_id: str, ts: pd.Timestamp) -> list[dict]:
        idx = self.rows_at(ts)
        idx = idx.index[idx["agent_id"] == agent_id]
        return self.detector.drivers(self.anom.loc[idx[0]]) if len(idx) else []

    def agent_history(self, agent_id: str, as_of: pd.Timestamp, hours: int = 72) -> pd.DataFrame:
        f = self.feats
        m = (f["agent_id"] == agent_id) & f["timestamp"].between(as_of - pd.Timedelta(hours=hours - 1), as_of)
        h = f.loc[m, ["timestamp", "cash_balance", "cash_out_amount", "cash_in_amount", "unmet_cash_out",
                      "transaction_count", "future_6h_cash_demand", "future_6h_net_cash_demand"]].copy()
        h = h.join(self.preds[["pred_cash_demand_6h", "pred_net_requirement_6h"]], how="left")
        h = h.join(self.anom[["anomaly_score"]], how="left")
        # targets that would only be known after as_of must not be shown as "actual"
        hidden = h["timestamp"] + pd.Timedelta(hours=config.HORIZON_H) > as_of
        h.loc[hidden, ["future_6h_cash_demand", "future_6h_net_cash_demand"]] = np.nan
        return h
