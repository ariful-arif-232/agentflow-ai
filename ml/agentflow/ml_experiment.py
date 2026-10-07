"""Phase-2 targeted ML experiment: can the peak-requirement forecast and the early-warning recall improve?

Controlled, pre-registered protocol (see docs/ML_EXPERIMENT.md):

1. **Selection on training-period validation folds only.** Each candidate is re-trained on rows whose 6-hour target
   window ends before the fold starts, and scored on the fold's rows whose target window also ends inside the fold
   (so fold B never sees a held-out hour). ``assert_selection_rows_before_test`` enforces this.
2. **Pre-registered success criteria** (``CRITERIA``) are fixed in code and hashed into the artifact before the
   held-out evaluation runs.
3. **One held-out evaluation** of the current serving model and the validation-selected candidates, followed by
   the promotion decision. A candidate that fails any criterion is rejected and the serving model is unchanged.

Candidate families
------------------
* **Spatial / neighbour aggregates** — same-district (excluding the agent itself) and 5 nearest outlets: mean
  cash-out regime ratio, mean transaction-velocity ratio and shortage share. Strictly lagged: neighbours'
  information up to hour ``t-1`` only (one hour of feed latency), computed from history-only columns.
* **Temporal regime features** — today's cash-out / cash-in so far against the same hours on the previous seven
  days, yesterday's daily total against its 7-day average, and the spread of the same-window history.
* **Ensemble** — average of three feature-bagged gradient-boosting models (different seeds) from the existing
  stack, optionally blended with the seasonal baseline (blend weight chosen on validation).
* **Alert operating point** — risk-score thresholds below the HIGH boundary, with the precision trade-off; the
  risk formula, its levels and everything that consumes them (rebalancing) are unchanged.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

from . import config, forecast, risk
from .engine import OPERATING_HOURS
from .features import FORECAST_FEATURES, TARGETS
from .rebalance import haversine_km

VERSION = "phase2-ml-1"
H = config.HORIZON_H
LABEL = "Synthetic controlled experiment — selection on training-period validation folds only; held-out evaluated once."

# Validation folds inside the training period (same windows as the V2 policy selection), purged so that every
# scored row's 6-hour target window ends inside the fold.
FOLDS = (
    {"name": "A", "val_start": pd.Timestamp("2026-07-21 00:00"), "val_end": pd.Timestamp("2026-08-03 23:00")},
    {"name": "B", "val_start": pd.Timestamp("2026-08-04 00:00"), "val_end": pd.Timestamp("2026-08-17 23:00")},
)

SPATIAL_FEATURES = ["nbr_district_out_regime", "nbr_district_velocity", "nbr_district_shortage_24h",
                    "nbr_knn_out_regime", "nbr_knn_velocity", "nbr_knn_shortage_24h"]
TEMPORAL_FEATURES = ["today_out_ratio", "today_in_ratio", "yesterday_out_ratio", "net_req_same_window_std7",
                     "out_regime_24h"]
KNN = 5
ALERT_THRESHOLDS = (50.0, 45.0, 40.0, 35.0, 30.0, 25.0)  # 50 = current HIGH boundary

# --------------------------------------------------------------------------- pre-registered criteria
CRITERIA = {
    "selection_rule_forecast": (
        "On the two validation folds combined, the candidate with the lowest peak-requirement MAE goes to the held-out "
        "evaluation only if it beats the current configuration's validation MAE by at least 1%, keeps validation P90 "
        "coverage within [0.87, 0.93] and does not worsen validation cash-demand MAE by more than 1%."),
    "selection_rule_alert": (
        "The lowest risk-score threshold in {50, 45, 40, 35, 30, 25} whose combined validation precision is at least "
        "0.70 (computed with fold-trained current models)."),
    "promotion_forecast": {
        "peak_mae_vs_current_max_ratio": 0.97,      # >= 3% lower held-out peak-requirement MAE than the serving model
        "peak_mae_vs_seasonal_min_improvement_pct": 10.0,  # and >= 10% better than the seasonal baseline (now 6.8%)
        "cash_demand_mae_vs_current_max_ratio": 1.01,
        "p90_coverage_range": [0.87, 0.93],
        "high_plus_recall_min_change_pp": -1.0,     # HIGH+ recall (unchanged thresholds) must not fall > 1 pp
        "high_plus_precision_min_change_pp": -5.0,
        "v2_unmet_max_ratio": 1.02,                 # downstream V2 on held-out vs current serving V2
        "v2_shortage_events_max_ratio": 1.02,
        "v2_donor_shortage_events_max_increase": 2,
        "leakage_tests_must_pass": True,
    },
    "promotion_alert_operating_point": {
        "recall_min_gain_pp": 10.0,                 # meaningful: >= +10 pp over HIGH+ recall
        "precision_min": 0.70,                      # no unacceptable collapse
        "alert_rate_max_multiple": 3.0,             # at most 3x the HIGH+ alert volume
        "scope": "early-warning alert definition only; risk levels and rebalancing recipients are unchanged",
    },
}


def criteria_hash() -> str:
    return hashlib.sha256(json.dumps(CRITERIA, sort_keys=True).encode()).hexdigest()


# --------------------------------------------------------------------------- candidate features
def add_candidate_features(feats: pd.DataFrame, agents: pd.DataFrame) -> pd.DataFrame:
    """Spatial and temporal candidate features. Uses only information at hours <= t (neighbours: <= t-1)."""
    df = feats.copy()
    gid = df["agent_id"]
    out, inn = df["cash_out_amount"].astype(float), df["cash_in_amount"].astype(float)
    day = df["timestamp"].dt.normalize()

    # --- temporal regime (own history only)
    cum_out = out.groupby([gid, day]).cumsum()
    cum_in = inn.groupby([gid, day]).cumsum()
    prev_out = pd.concat([cum_out.groupby(gid).shift(24 * d) for d in range(1, 8)], axis=1).mean(axis=1, skipna=False)
    prev_in = pd.concat([cum_in.groupby(gid).shift(24 * d) for d in range(1, 8)], axis=1).mean(axis=1, skipna=False)
    df["today_out_ratio"] = (cum_out + 500.0) / (prev_out + 500.0)
    df["today_in_ratio"] = (cum_in + 500.0) / (prev_in + 500.0)
    daily_out = out.groupby([gid, day]).transform("sum")
    # yesterday's total is fully observed at any hour of today: shift by (hour + 1) hours back to yesterday 23:00
    hour = df["hour"].astype(int).to_numpy()
    y_tot = np.full(len(df), np.nan)
    shifted = {h: daily_out.groupby(gid).shift(h + 1).to_numpy() for h in range(24)}
    for h in range(24):
        m = hour == h
        y_tot[m] = shifted[h][m]
    df["yesterday_out_total"] = y_tot
    avg7_daily = df.groupby(gid)["yesterday_out_total"].transform(lambda s: s.shift(24).rolling(24 * 7, min_periods=24 * 7).mean())
    df["yesterday_out_ratio"] = (df["yesterday_out_total"] + 1000.0) / (avg7_daily + 1000.0)
    lags = pd.concat([df["future_6h_net_cash_demand"].groupby(gid).shift(24 * d) for d in range(1, 8)], axis=1)
    df["net_req_same_window_std7"] = lags.std(axis=1, skipna=False)
    df["out_regime_24h"] = (df["out_sum_24h"] + 1000.0) / (24 * df["out_rolling_mean_168h"] + 1000.0)

    # --- spatial / neighbour aggregates, lagged one hour (neighbour info <= t-1)
    sh_24 = df["liquidity_shortage"].astype(float).groupby(gid).rolling(24, min_periods=24).mean().reset_index(level=0, drop=True)
    base = pd.DataFrame({"agent_id": gid, "timestamp": df["timestamp"], "district": df["district"],
                         "regime": df["out_regime_24h"], "velocity": df["velocity_ratio_3h"], "short24": sh_24})
    for c in ("regime", "velocity", "short24"):
        base[c] = base.groupby("agent_id")[c].shift(1)
    # district mean excluding self
    grp = base.groupby(["timestamp", "district"])
    for c, name in (("regime", "nbr_district_out_regime"), ("velocity", "nbr_district_velocity"),
                    ("short24", "nbr_district_shortage_24h")):
        s, n = grp[c].transform("sum"), grp[c].transform("count")
        own = base[c]
        df[name] = ((s - own.fillna(0)) / (n - own.notna().astype(int))).where(n - own.notna().astype(int) > 0)
    # k nearest outlets (any district, excluding self)
    ag = agents.set_index("agent_id")
    ids = list(ag.index)
    lat, lon = ag["synthetic_latitude"].to_numpy(), ag["synthetic_longitude"].to_numpy()
    d = haversine_km(lat[:, None], lon[:, None], lat[None, :], lon[None, :])
    np.fill_diagonal(d, np.inf)
    nbrs = {ids[i]: [ids[j] for j in np.argsort(d[i])[:KNN]] for i in range(len(ids))}
    for c, name in (("regime", "nbr_knn_out_regime"), ("velocity", "nbr_knn_velocity"), ("short24", "nbr_knn_shortage_24h")):
        wide = base.pivot(index="timestamp", columns="agent_id", values=c)
        knn = pd.DataFrame({a: wide[nbrs[a]].mean(axis=1, skipna=False) for a in ids}, index=wide.index)
        knn.columns.name = "agent_id"
        long = knn.stack(future_stack=True).rename(name).reset_index()
        df[name] = df[["timestamp", "agent_id"]].merge(long, on=["timestamp", "agent_id"], how="left")[name].to_numpy()
    return df


CANDIDATES = {
    "current": {"features": [], "ensemble": False, "blend": False,
                "desc": "Serving configuration (reference)"},
    "spatial": {"features": SPATIAL_FEATURES, "ensemble": False, "blend": False,
                "desc": "+ lagged same-district and 5-nearest-outlet aggregates"},
    "temporal": {"features": TEMPORAL_FEATURES, "ensemble": False, "blend": False,
                 "desc": "+ temporal regime features (today so far vs normal, yesterday vs normal, window spread)"},
    "spatial_temporal": {"features": SPATIAL_FEATURES + TEMPORAL_FEATURES, "ensemble": False, "blend": False,
                         "desc": "+ spatial and temporal features"},
    "temporal_ensemble": {"features": TEMPORAL_FEATURES, "ensemble": True, "blend": True,
                          "desc": "temporal features, 3 feature-bagged seeds averaged, blended with the seasonal baseline"},
}


# --------------------------------------------------------------------------- candidate model
def _gbm(loss, quantile, feats, seed, max_features=1.0, max_iter=400):
    cat_mask = [f in forecast.CATEGORICAL_FEATURES for f in feats]
    kw = dict(loss=loss, learning_rate=0.06, max_iter=max_iter, max_leaf_nodes=48, min_samples_leaf=60,
              l2_regularization=1.0, categorical_features=cat_mask, early_stopping=False, random_state=seed,
              max_features=max_features)
    if quantile is not None:
        kw["quantile"] = quantile
    return HistGradientBoostingRegressor(**kw)


@dataclass
class CandidateModel:
    name: str
    features: list[str]
    ensemble: bool
    blend: bool
    models: dict = field(default_factory=dict)
    blend_weight: float = 0.0

    def fit(self, df: pd.DataFrame, max_iter: int = 400) -> "CandidateModel":
        X = df[self.features]
        seeds = (config.SEED, config.SEED + 1, config.SEED + 2) if self.ensemble else (config.SEED,)
        mf = 0.8 if self.ensemble else 1.0
        for name, spec in forecast.MODEL_SPECS.items():
            self.models[name] = [_gbm(spec["loss"], spec["quantile"], self.features, s, mf, max_iter)
                                 .fit(X, df[spec["target"]].to_numpy()) for s in seeds]
        return self

    def predict(self, df: pd.DataFrame) -> pd.DataFrame:
        X = df[self.features]
        avg = {k: np.mean([m.predict(X) for m in ms], axis=0) for k, ms in self.models.items()}
        w = self.blend_weight
        cash = np.clip(avg["cash_demand"], 0, None)
        p50 = np.clip(avg["net_requirement"], 0, None)
        if w:
            cash = (1 - w) * cash + w * df["out_same_window_avg7"].to_numpy()
            p50 = (1 - w) * p50 + w * df["net_req_same_window_avg7"].to_numpy()
        p90 = np.maximum(np.clip(avg["net_requirement_p90"], 0, None), p50)
        return pd.DataFrame({"pred_cash_demand_6h": cash, "pred_net_requirement_6h": p50,
                             "pred_net_requirement_p90_6h": p90}, index=df.index)


def make_candidate(name: str) -> CandidateModel:
    c = CANDIDATES[name]
    return CandidateModel(name=name, features=list(FORECAST_FEATURES) + list(c["features"]),
                          ensemble=c["ensemble"], blend=c["blend"])


# --------------------------------------------------------------------------- evaluation helpers
def forecast_scores(df: pd.DataFrame, p: pd.DataFrame) -> dict:
    y_net, y_cash = df["future_6h_net_cash_demand"].to_numpy(), df["future_6h_cash_demand"].to_numpy()
    return {
        "peak_requirement_mae": float(np.mean(np.abs(p["pred_net_requirement_6h"].to_numpy() - y_net))),
        "cash_demand_mae": float(np.mean(np.abs(p["pred_cash_demand_6h"].to_numpy() - y_cash))),
        "seasonal_peak_mae": float(np.mean(np.abs(df["net_req_same_window_avg7"].to_numpy() - y_net))),
        "seasonal_cash_mae": float(np.mean(np.abs(df["out_same_window_avg7"].to_numpy() - y_cash))),
        "p90_coverage": float(np.mean(y_net <= p["pred_net_requirement_p90_6h"].to_numpy())),
        "n": int(len(df)),
    }


def alert_scores(df: pd.DataFrame, p: pd.DataFrame, hist_rate: pd.Series, thresholds=ALERT_THRESHOLDS) -> dict:
    """Early-warning evaluation on operating hours (same definition as evaluation.risk_alert_evaluation)."""
    d = df[df["hour"].isin(OPERATING_HOURS) & df["shortage_next_6h"].notna()]
    pp = p.reindex(d.index)
    y = d["shortage_next_6h"].to_numpy().astype(bool)
    r = risk.compute_risk(d["cash_balance"].to_numpy(), pp["pred_net_requirement_6h"].to_numpy(),
                          pp["pred_net_requirement_p90_6h"].to_numpy(), d["velocity_ratio_3h"].to_numpy(),
                          d["agent_id"].map(hist_rate).fillna(0).to_numpy())
    score = r["risk_score"].to_numpy()
    out = {"n_decisions": int(len(d)), "shortages": int(y.sum()), "thresholds": {}}
    for t in thresholds:
        a = score >= t
        tp, fp = int((a & y).sum()), int((a & ~y).sum())
        out["thresholds"][f"{t:g}"] = {"alerts": int(a.sum()), "alert_rate": float(a.mean()), "true_positives": tp,
                                       "false_positives": fp, "precision": tp / max(tp + fp, 1),
                                       "recall": tp / max(int(y.sum()), 1)}
    return out


def combine_alerts(parts: list[dict]) -> dict:
    out = {"n_decisions": sum(p["n_decisions"] for p in parts), "shortages": sum(p["shortages"] for p in parts),
           "thresholds": {}}
    for t in parts[0]["thresholds"]:
        tp = sum(p["thresholds"][t]["true_positives"] for p in parts)
        fp = sum(p["thresholds"][t]["false_positives"] for p in parts)
        al = sum(p["thresholds"][t]["alerts"] for p in parts)
        out["thresholds"][t] = {"alerts": al, "alert_rate": al / out["n_decisions"], "true_positives": tp,
                                "false_positives": fp, "precision": tp / max(tp + fp, 1),
                                "recall": tp / max(out["shortages"], 1)}
    return out


def _usable(df: pd.DataFrame) -> pd.Series:
    return df["out_same_window_avg7"].notna() & df["out_rolling_mean_168h"].notna() & df[TARGETS].notna().all(axis=1)


def fold_frames(df: pd.DataFrame, fold: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    ok = _usable(df)
    dev = df[ok & (df["timestamp"] < fold["val_start"] - pd.Timedelta(hours=H))]
    val = df[ok & df["timestamp"].between(fold["val_start"], fold["val_end"] - pd.Timedelta(hours=H))]
    return dev, val


def assert_selection_rows_before_test(*frames: pd.DataFrame) -> None:
    """No selection-stage row, and no hour inside its 6-hour target window, may reach the held-out period."""
    for f in frames:
        if len(f) and f["timestamp"].max() + pd.Timedelta(hours=H) >= config.TEST_START:
            raise ValueError("selection data reaches the held-out test period")
