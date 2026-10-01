"""Liquidity demand forecasting: naive baselines + gradient-boosted ML models.

Three models are trained on the same leakage-safe feature set:

* ``cash_demand``      — next-6h requested cash-out (point forecast)
* ``net_requirement``  — next-6h peak cumulative net cash drain (point forecast)
* ``net_requirement_p90`` — 90th-percentile quantile model of the same target,
  used as the forecast-uncertainty upper band and as the rebalancing target level.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.inspection import permutation_importance

from . import config
from .features import FORECAST_FEATURES

MODEL_PATH = config.MODELS_DIR / "forecast_models.joblib"

CATEGORICAL_FEATURES = ["district_code", "location_cluster_code", "agent_volume_segment_code",
                        "agent_type_code", "day_of_week"]

MODEL_SPECS = {
    "cash_demand": {"target": "future_6h_cash_demand", "loss": "poisson", "quantile": None},
    "net_requirement": {"target": "future_6h_net_cash_demand", "loss": "squared_error", "quantile": None},
    "net_requirement_p90": {"target": "future_6h_net_cash_demand", "loss": "quantile", "quantile": 0.9},
}

# Naive baselines evaluated on exactly the same held-out rows.
BASELINES = {
    "cash_demand": {
        "naive_yesterday": "out_same_window_1d",
        "seasonal_avg_7d": "out_same_window_avg7",
    },
    "net_requirement": {
        "naive_yesterday": "net_req_same_window_1d",
        "seasonal_avg_7d": "net_req_same_window_avg7",
    },
}


def _make_model(loss: str, quantile: float | None, max_iter: int = 400) -> HistGradientBoostingRegressor:
    cat_mask = [f in CATEGORICAL_FEATURES for f in FORECAST_FEATURES]
    kwargs = dict(loss=loss, learning_rate=0.06, max_iter=max_iter, max_leaf_nodes=48,
                  min_samples_leaf=60, l2_regularization=1.0, categorical_features=cat_mask,
                  early_stopping=False, random_state=config.SEED)
    if quantile is not None:
        kwargs["quantile"] = quantile
    return HistGradientBoostingRegressor(**kwargs)


def regression_metrics(y: np.ndarray, p: np.ndarray) -> dict:
    y = np.asarray(y, float)
    p = np.asarray(p, float)
    err = p - y
    return {
        "mae": float(np.mean(np.abs(err))),
        "rmse": float(np.sqrt(np.mean(err ** 2))),
        # Weighted absolute percentage error: sum|e| / sum|y| — well-defined with zeros.
        "wape": float(np.sum(np.abs(err)) / max(np.sum(np.abs(y)), 1e-9)),
        "bias": float(np.mean(err)),
        "n": int(len(y)),
    }


@dataclass
class ForecastBundle:
    models: dict[str, HistGradientBoostingRegressor]
    features: list[str]
    metadata: dict

    def predict(self, X: pd.DataFrame) -> pd.DataFrame:
        X = X[self.features]
        out = pd.DataFrame(index=X.index)
        out["pred_cash_demand_6h"] = np.clip(self.models["cash_demand"].predict(X), 0, None)
        p50 = np.clip(self.models["net_requirement"].predict(X), 0, None)
        p90 = np.clip(self.models["net_requirement_p90"].predict(X), 0, None)
        out["pred_net_requirement_6h"] = p50
        out["pred_net_requirement_p90_6h"] = np.maximum(p90, p50)  # enforce non-crossing
        return out

    def save(self, path=MODEL_PATH) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump({"models": self.models, "features": self.features, "metadata": self.metadata},
                    path, compress=3)

    @classmethod
    def load(cls, path=MODEL_PATH) -> "ForecastBundle":
        d = joblib.load(path)
        return cls(models=d["models"], features=d["features"], metadata=d["metadata"])


def train(train_df: pd.DataFrame, max_iter: int = 400) -> ForecastBundle:
    models = {}
    timings = {}
    X = train_df[FORECAST_FEATURES]
    for name, spec in MODEL_SPECS.items():
        t0 = time.time()
        m = _make_model(spec["loss"], spec["quantile"], max_iter)
        m.fit(X, train_df[spec["target"]].to_numpy())
        models[name] = m
        timings[name] = round(time.time() - t0, 2)
    meta = {
        "algorithm": "sklearn.ensemble.HistGradientBoostingRegressor",
        "model_specs": MODEL_SPECS,
        "n_train_rows": int(len(train_df)),
        "train_start": str(train_df["timestamp"].min()),
        "train_end": str(train_df["timestamp"].max()),
        "fit_seconds": timings,
        "seed": config.SEED,
        "horizon_hours": config.HORIZON_H,
    }
    return ForecastBundle(models=models, features=list(FORECAST_FEATURES), metadata=meta)


def evaluate(bundle: ForecastBundle, test_df: pd.DataFrame) -> dict:
    preds = bundle.predict(test_df)
    res: dict = {"test_start": str(test_df["timestamp"].min()), "test_end": str(test_df["timestamp"].max()),
                 "n_test_rows": int(len(test_df)), "targets": {}}
    for name, col in (("cash_demand", "pred_cash_demand_6h"), ("net_requirement", "pred_net_requirement_6h")):
        target = MODEL_SPECS[name]["target"]
        y = test_df[target].to_numpy()
        entry = {"target": target, "ml_model": regression_metrics(y, preds[col]), "baselines": {}}
        for b_name, b_col in BASELINES[name].items():
            entry["baselines"][b_name] = regression_metrics(y, test_df[b_col].to_numpy())
        best_b = min(entry["baselines"], key=lambda k: entry["baselines"][k]["mae"])
        entry["best_baseline"] = best_b
        bm = entry["baselines"][best_b]
        entry["improvement_vs_best_baseline"] = {
            "mae_pct": 100 * (1 - entry["ml_model"]["mae"] / bm["mae"]),
            "rmse_pct": 100 * (1 - entry["ml_model"]["rmse"] / bm["rmse"]),
        }
        nb = entry["baselines"]["naive_yesterday"]
        entry["improvement_vs_naive"] = {
            "mae_pct": 100 * (1 - entry["ml_model"]["mae"] / nb["mae"]),
            "rmse_pct": 100 * (1 - entry["ml_model"]["rmse"] / nb["rmse"]),
        }
        res["targets"][name] = entry
    y = test_df["future_6h_net_cash_demand"].to_numpy()
    res["quantile_p90"] = {
        "target": "future_6h_net_cash_demand",
        "empirical_coverage": float(np.mean(y <= preds["pred_net_requirement_p90_6h"].to_numpy())),
        "nominal_coverage": 0.9,
        "mean_band_width": float(np.mean(preds["pred_net_requirement_p90_6h"] - preds["pred_net_requirement_6h"])),
    }
    # Operational-group consistency (no personal attributes exist in the data).
    groups = {}
    for gcol in ("location_cluster", "agent_volume_segment"):
        groups[gcol] = {}
        for g, idx in test_df.groupby(gcol).groups.items():
            sub = test_df.loc[idx]
            y_g = sub["future_6h_cash_demand"].to_numpy()
            ml = regression_metrics(y_g, preds.loc[idx, "pred_cash_demand_6h"])
            nv = regression_metrics(y_g, sub["out_same_window_1d"].to_numpy())
            groups[gcol][str(g)] = {"ml_mae": ml["mae"], "ml_wape": ml["wape"],
                                    "naive_mae": nv["mae"], "naive_wape": nv["wape"], "n": ml["n"]}
    res["group_consistency"] = groups
    return res


def feature_importance(bundle: ForecastBundle, df: pd.DataFrame, n: int = 15000) -> list[dict]:
    """Permutation importance (MAE increase) of the cash-demand model on held-out rows."""
    sample = df.sample(n=min(n, len(df)), random_state=config.SEED)
    r = permutation_importance(bundle.models["cash_demand"], sample[bundle.features],
                               sample["future_6h_cash_demand"], scoring="neg_mean_absolute_error",
                               n_repeats=3, random_state=config.SEED, n_jobs=1)
    rows = [{"feature": f, "mae_increase": float(m), "std": float(s)}
            for f, m, s in zip(bundle.features, r.importances_mean, r.importances_std)]
    return sorted(rows, key=lambda d: -d["mae_increase"])


def write_json(path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, default=float))
