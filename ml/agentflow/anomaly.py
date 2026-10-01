"""Behavioural anomaly detection (Isolation Forest on agent-relative deviations).

Outputs a continuous anomaly score and a status: NORMAL / WATCH / ANOMALOUS.
A behavioural anomaly means *unusual activity relative to the agent's own history* —
it is a prompt for manual review, never a fraud determination.
"""
from __future__ import annotations

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.metrics import average_precision_score, roc_auc_score

from . import config

MODEL_PATH = config.MODELS_DIR / "anomaly_model.joblib"

ANOMALY_FEATURES = [
    "dev_cash_out", "dev_cash_in", "dev_txn_count", "dev_ticket", "churn_score",
    "night_activity", "dev_velocity",
]

FEATURE_LABELS = {
    "dev_cash_out": "cash-out amount vs. the agent's usual level for this hour",
    "dev_cash_in": "cash-in amount vs. the agent's usual level for this hour",
    "dev_txn_count": "cash-out transaction count vs. the agent's usual level for this hour",
    "dev_ticket": "average cash-out ticket size vs. the agent's 7-day average",
    "churn_score": "simultaneous cash-in and cash-out surge",
    "night_activity": "activity during night hours (00:00-05:59)",
    "dev_velocity": "3-hour transaction velocity vs. the same hours on previous days",
}

# Status thresholds are quantiles of the *training-period* score distribution.
WATCH_Q = 0.990
ANOMALOUS_Q = 0.997


def anomaly_features(df: pd.DataFrame) -> pd.DataFrame:
    """Agent-relative deviation features (history only: same hour on the previous 7 days)."""
    gid = df["agent_id"]

    def same_hour_avg(col: str) -> pd.Series:
        g = df[col].astype(float).groupby(gid)
        return pd.concat([g.shift(24 * d) for d in range(1, 8)], axis=1).mean(axis=1, skipna=False)

    out = df["cash_out_amount"].astype(float)
    inn = df["cash_in_amount"].astype(float)
    cnt = df["transaction_count"].astype(float)
    f = pd.DataFrame(index=df.index)
    f["dev_cash_out"] = np.log1p(out) - np.log1p(same_hour_avg("cash_out_amount"))
    f["dev_cash_in"] = np.log1p(inn) - np.log1p(same_hour_avg("cash_in_amount"))
    out_cnt = df["cash_out_count"].astype(float)
    f["dev_txn_count"] = np.log1p(out_cnt) - np.log1p(same_hour_avg("cash_out_count"))
    amt_168 = out.groupby(gid).rolling(168, min_periods=168).sum().reset_index(level=0, drop=True)
    cnt_168 = out_cnt.groupby(gid).rolling(168, min_periods=168).sum().reset_index(level=0, drop=True)
    same_agent = gid.eq(gid.shift(1))
    base_ticket = amt_168.shift(1).where(same_agent) / (cnt_168.shift(1).where(same_agent) + 1.0)
    ticket = out / out_cnt.clip(lower=1.0)
    f["dev_ticket"] = np.log((ticket + 200.0) / (base_ticket + 200.0))
    f["churn_score"] = np.minimum(f["dev_cash_out"], f["dev_cash_in"])
    f["night_activity"] = (df["hour"] < 6).astype(float) * np.log1p(cnt)
    f["dev_velocity"] = np.log(df["velocity_ratio_3h"].astype(float) + 0.1)
    # Review-relevant behaviour is a *surge* (or an unusual ticket size in either
    # direction); quieter-than-usual hours are not flagged, so deviations are one-sided.
    for c in ("dev_cash_out", "dev_cash_in", "dev_txn_count", "churn_score", "dev_velocity"):
        f[c] = f[c].clip(lower=0)
    f["dev_ticket"] = f["dev_ticket"].abs()
    return f


class AnomalyDetector:
    """Hybrid detector: Isolation Forest + robust per-feature deviation rule.

    Each component score is mapped to its training-period percentile and the two
    percentiles are averaged. The Isolation Forest captures unusual *combinations* of
    features; the robust rule captures extreme single-feature surges. Held-out results
    for each component and for the hybrid are reported in ml/artifacts/metrics.json.
    """

    def __init__(self, model: IsolationForest | None = None, thresholds: dict | None = None,
                 feature_stats: dict | None = None, ref: dict | None = None):
        self.model = model
        self.thresholds = thresholds or {}
        self.feature_stats = feature_stats or {}
        self.ref = ref or {}

    def fit(self, feats: pd.DataFrame) -> "AnomalyDetector":
        X = feats[ANOMALY_FEATURES].dropna()
        self.model = IsolationForest(n_estimators=200, max_samples=8192, contamination="auto",
                                     random_state=config.SEED, n_jobs=-1).fit(X)
        self.feature_stats = {}
        for c in ANOMALY_FEATURES:
            iqr = float(X[c].quantile(0.75) - X[c].quantile(0.25))
            self.feature_stats[c] = {"median": float(X[c].median()),
                                     "iqr": iqr if iqr > 1e-6 else float(X[c].std() or 1.0)}
        grid = np.linspace(0, 1, 2001)
        self.ref = {"iforest": np.quantile(self.iforest_score(X), grid),
                    "rule": np.quantile(self.rule_score(X), grid)}
        scores = self.score(X)
        self.thresholds = {"watch": float(np.quantile(scores, WATCH_Q)),
                           "anomalous": float(np.quantile(scores, ANOMALOUS_Q))}
        return self

    def iforest_score(self, X: pd.DataFrame) -> np.ndarray:
        return -self.model.score_samples(X[ANOMALY_FEATURES])

    def rule_score(self, X: pd.DataFrame) -> np.ndarray:
        z = [(X[c].to_numpy() - self.feature_stats[c]["median"]) / self.feature_stats[c]["iqr"]
             for c in ANOMALY_FEATURES]
        return np.max(np.column_stack(z), axis=1)

    @staticmethod
    def _pct(ref: np.ndarray, x: np.ndarray) -> np.ndarray:
        return np.interp(x, ref, np.linspace(0, 1, len(ref)))

    def score(self, X: pd.DataFrame, component: str = "hybrid") -> np.ndarray:
        """Higher = more anomalous, in [0, 1]. Rows with insufficient history score 0."""
        X = X[ANOMALY_FEATURES]
        ok = X.notna().all(axis=1).to_numpy()
        s = np.zeros(len(X))
        if ok.any():
            Xo = X[ok]
            p_if = self._pct(self.ref["iforest"], self.iforest_score(Xo))
            p_rule = self._pct(self.ref["rule"], self.rule_score(Xo))
            s[ok] = {"hybrid": 0.5 * (p_if + p_rule), "iforest": p_if, "rule": p_rule}[component]
        return s

    def status(self, scores: np.ndarray) -> np.ndarray:
        return np.where(scores >= self.thresholds["anomalous"], "ANOMALOUS",
                        np.where(scores >= self.thresholds["watch"], "WATCH", "NORMAL"))

    def drivers(self, row: pd.Series, top: int = 3) -> list[dict]:
        """Most deviating features of one observation (robust z vs. training distribution)."""
        out = []
        for c in ANOMALY_FEATURES:
            st = self.feature_stats[c]
            v = float(row[c])
            if np.isnan(v):
                continue
            z = (v - st["median"]) / st["iqr"]
            ratio = float(np.exp(v)) if c != "night_activity" else None
            out.append({"feature": c, "description": FEATURE_LABELS[c], "robust_z": round(z, 2),
                        "ratio_vs_usual": round(ratio, 2) if ratio is not None else None})
        out.sort(key=lambda d: -d["robust_z"])
        return out[:top]

    def save(self, path=MODEL_PATH) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump({"model": self.model, "thresholds": self.thresholds,
                     "feature_stats": self.feature_stats, "ref": self.ref}, path, compress=3)

    @classmethod
    def load(cls, path=MODEL_PATH) -> "AnomalyDetector":
        d = joblib.load(path)
        return cls(d["model"], d["thresholds"], d["feature_stats"], d["ref"])


def evaluate(detector: AnomalyDetector, feats: pd.DataFrame, labels: pd.Series,
             types: pd.Series) -> dict:
    ok = feats[ANOMALY_FEATURES].notna().all(axis=1)
    X, y, t = feats[ok], labels[ok].to_numpy(), types[ok]
    s = detector.score(X)
    status = detector.status(s)
    res = {"n_rows": int(len(y)), "n_labelled_anomalies": int(y.sum()),
           "roc_auc": float(roc_auc_score(y, s)), "average_precision": float(average_precision_score(y, s)),
           "prevalence": float(y.mean()), "thresholds": detector.thresholds, "by_status": {}}
    for level, mask in (("WATCH_or_higher", status != "NORMAL"), ("ANOMALOUS", status == "ANOMALOUS")):
        tp = int((mask & (y == 1)).sum())
        res["by_status"][level] = {"flagged": int(mask.sum()), "true_positives": tp,
                                   "precision": tp / max(int(mask.sum()), 1),
                                   "recall": tp / max(int(y.sum()), 1)}
    flagged = status != "NORMAL"
    res["recall_by_type_watch_or_higher"] = {
        k: float(flagged[(t == k).to_numpy()].mean()) for k in sorted(set(t[y == 1]))}
    res["components"] = {}
    for comp in ("iforest", "rule", "hybrid"):
        sc = detector.score(X, comp)
        res["components"][comp] = {"roc_auc": float(roc_auc_score(y, sc)),
                                   "average_precision": float(average_precision_score(y, sc))}
    return res
