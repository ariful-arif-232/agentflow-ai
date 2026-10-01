"""Held-out evaluation of the risk engine as an early-warning system."""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

from . import config, risk
from .engine import OPERATING_HOURS


def _alert_metrics(y: np.ndarray, alert: np.ndarray, score: np.ndarray) -> dict:
    tp = int((alert & y).sum())
    fp = int((alert & ~y).sum())
    fn = int((~alert & y).sum())
    p = tp / max(tp + fp, 1)
    r = tp / max(tp + fn, 1)
    return {"alerts": int(alert.sum()), "alert_rate": float(alert.mean()), "true_positives": tp,
            "false_positives": fp, "missed_shortages": fn, "precision": p, "recall": r,
            "f1": 2 * p * r / max(p + r, 1e-9), "roc_auc": float(roc_auc_score(y, score))}


def risk_alert_evaluation(test_df: pd.DataFrame, preds: pd.DataFrame, hist_rate: pd.Series) -> dict:
    """Does a HIGH/CRITICAL alert at hour t anticipate a real shortage in t+1..t+6?

    Evaluated on held-out operating hours (08:00-21:00) using the status-quo cash path.
    The same deterministic risk engine is fed (a) ML forecasts and (b) naive seasonal
    baseline forecasts, isolating the value added by the ML forecast.
    """
    d = test_df[test_df["hour"].isin(OPERATING_HOURS) & test_df["shortage_next_6h"].notna()]
    p = preds.reindex(d.index)
    y = d["shortage_next_6h"].to_numpy().astype(bool)
    hist = d["agent_id"].map(hist_rate).fillna(0).to_numpy()
    variants = {
        "ml_forecast": (p["pred_net_requirement_6h"], p["pred_net_requirement_p90_6h"]),
        "naive_seasonal_forecast": (d["net_req_same_window_avg7"], d["net_req_same_window_max7"]),
    }
    out = {"label": "Synthetic held-out evaluation", "n_decisions": int(len(d)),
           "shortage_prevalence": float(y.mean()), "alert_definition": "risk_level in {HIGH, CRITICAL}",
           "variants": {}}
    for name, (p50, p90) in variants.items():
        r = risk.compute_risk(d["cash_balance"].to_numpy(), p50.to_numpy(), p90.to_numpy(),
                              d["velocity_ratio_3h"].to_numpy(), hist)
        alert = r["risk_level"].isin(["HIGH", "CRITICAL"]).to_numpy()
        out["variants"][name] = _alert_metrics(y, alert, r["risk_score"].to_numpy())
        if name == "ml_forecast":
            groups = {}
            for gcol in ("location_cluster", "agent_volume_segment"):
                groups[gcol] = {}
                for g in sorted(d[gcol].unique()):
                    m = (d[gcol] == g).to_numpy()
                    groups[gcol][g] = {k: v for k, v in _alert_metrics(y[m], alert[m], r["risk_score"].to_numpy()[m]).items()
                                       if k in ("alert_rate", "precision", "recall", "f1")}
                    groups[gcol][g]["shortage_prevalence"] = float(y[m].mean())
            out["group_consistency"] = groups
            levels = {}
            for lvl in ("LOW", "MEDIUM", "HIGH", "CRITICAL"):
                m = (r["risk_level"] == lvl).to_numpy()
                levels[lvl] = {"share_of_decisions": float(m.mean()),
                               "observed_shortage_rate": float(y[m].mean()) if m.any() else None}
            out["calibration_by_level"] = levels
    return out
