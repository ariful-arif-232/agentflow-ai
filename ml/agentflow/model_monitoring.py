"""Read-only, retrospective input monitoring; never changes a model or decision.

PSI bins are fitted on training inputs only. Missing/invalid values are counted
separately, not imputed or silently marked stable. Thresholds are illustrative
review rules, not significance tests or guarantees of forecast performance.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

VERSION = "phase2-monitoring-1"
LABEL = "Synthetic monitoring prototype - not live upay telemetry."
FEATURES = {
    "out_last_1h": "Latest hourly cash-out",
    "out_same_window_avg7": "7-day same-window cash-out",
    "out_rolling_mean_168h": "7-day average hourly cash-out",
    "in_sum_6h": "Recent 6-hour cash-in",
    "txn_count_3h": "Recent 3-hour transaction count",
    "velocity_ratio_3h": "Transaction velocity ratio",
}
WATCH = 0.10
DRIFT = 0.25
MIN_SAMPLES = 100
EPSILON = 1e-6


def status_for(psi: float | None) -> str:
    if psi is None or not np.isfinite(psi):
        return "INSUFFICIENT_DATA"
    return "DRIFT" if psi >= DRIFT else "WATCH" if psi >= WATCH else "STABLE"


def values_and_quality(series: pd.Series, integer: bool = False) -> tuple[np.ndarray, dict]:
    """Disjoint quality counts. All monitored inputs are non-negative by definition."""
    missing = series.isna().to_numpy()
    numbers = pd.to_numeric(series, errors="coerce").to_numpy(dtype=float, na_value=np.nan)
    finite = np.isfinite(numbers)
    invalid = ~missing & ~finite
    out_of_range = finite & (numbers < 0)
    if integer:
        out_of_range |= finite & (numbers != np.floor(numbers))
    valid = finite & ~out_of_range
    quality = {"rows": len(series), "missing": int(missing.sum()), "invalid": int(invalid.sum()),
               "out_of_range": int(out_of_range.sum()), "valid": int(valid.sum())}
    return numbers[valid], quality


def feature_report(reference: pd.Series, current: pd.Series, name: str) -> dict:
    ref, rq = values_and_quality(reference, integer=name == "txn_count_3h")
    cur, cq = values_and_quality(current, integer=name == "txn_count_3h")
    out = {"name": name, "label": FEATURES.get(name, name), "reference_quality": rq, "current_quality": cq,
           "psi": None, "status": "INSUFFICIENT_DATA", "bin_edges": [], "reference_fractions": [],
           "current_fractions": []}
    if min(len(ref), len(cur)) < MIN_SAMPLES:
        return out
    if np.min(ref) == np.max(ref):
        # Isolate a constant reference value so both upward and downward shifts remain visible.
        value = float(ref[0])
        inner = np.array([value, np.nextafter(value, np.inf)])
        inner = inner[np.isfinite(inner)]
    else:
        inner = np.unique(np.quantile(ref, np.arange(1, 10) / 10))
    edges = np.r_[-np.inf, inner, np.inf]
    r = np.histogram(ref, bins=edges)[0] / len(ref)
    c = np.histogram(cur, bins=edges)[0] / len(cur)
    # Equal probability smoothing (then normalise) avoids division by zero without
    # manufacturing a shift when sample counts differ but the proportions match.
    rs, cs = r + EPSILON, c + EPSILON
    rs, cs = rs / rs.sum(), cs / cs.sum()
    psi = float(np.sum((cs - rs) * np.log(cs / rs)))
    out.update(psi=psi, status=status_for(psi),
               bin_edges=["-inf", *[float(x) for x in inner], "+inf"],
               reference_fractions=r.tolist(), current_fractions=c.tolist())
    return out


def build_report(feats: pd.DataFrame, test_start, horizon_hours: int = 6) -> dict:
    """Compare post-warm-up training inputs with held-out inputs, never future targets.

    Keep missing values in the quality denominator. Do NOT use time_split/dropna:
    complete-case filtering would hide exactly the data-quality faults being checked.
    The final held-out hours are included even when future target labels are unknown.
    """
    ts = pd.to_datetime(feats["timestamp"], errors="raise")
    if ts.empty or ts.isna().any():
        raise ValueError("Monitoring requires non-empty, valid timestamps")
    if ts.dt.tz is not None:
        raise ValueError("Use the project's timezone-naive Asia/Dhaka timestamps")
    cut = pd.Timestamp(test_start)
    warmup_end = ts.min() + pd.Timedelta(hours=168)
    train = (ts >= warmup_end) & (ts < cut - pd.Timedelta(hours=horizon_hours))
    held_out = (ts >= cut) & (ts >= warmup_end)

    def population(mask):
        dates = ts[mask]
        return {"rows": int(mask.sum()), "start": dates.min().isoformat() if len(dates) else None,
                "end": dates.max().isoformat() if len(dates) else None}

    rows = []
    absent = []
    for name in FEATURES:
        if name not in feats:
            absent.append(name)
            col = pd.Series(np.nan, index=feats.index)
        else:
            col = feats[name]
        rows.append(feature_report(col.loc[train], col.loc[held_out], name))
    statuses = {s: sum(r["status"] == s for r in rows) for s in ("STABLE", "WATCH", "DRIFT", "INSUFFICIENT_DATA")}
    quality = {period: {kind: sum(r[f"{period}_quality"][kind] for r in rows)
                        for kind in ("missing", "invalid", "out_of_range")}
               for period in ("reference", "current")}
    needs_review = bool(absent or statuses["WATCH"] or statuses["DRIFT"] or statuses["INSUFFICIENT_DATA"]
                        or any(sum(q.values()) for q in quality.values()))
    return {
        "version": VERSION, "label": LABEL, "scope": "legacy intraday input features only; Morning Plan excluded",
        "mode": "offline historical train-versus-held-out comparison; not a live freshness or accuracy monitor",
        "reference": population(train), "current": population(held_out), "timezone": "Asia/Dhaka",
        "warmup_rows_excluded": int((ts < warmup_end).sum()),
        "purge_rows_excluded": int(((ts >= warmup_end) & (ts >= cut - pd.Timedelta(hours=horizon_hours)) & (ts < cut)).sum()),
        "missing_columns": absent,
        "method": {"name": "Population Stability Index (PSI)", "formula": "sum((current-reference)*ln(current/reference))",
                   "binning": "up to 10 training-quantile bins; constant reference isolated; open-ended tails",
                   "smoothing_probability": EPSILON, "minimum_valid_samples_per_window": MIN_SAMPLES,
                   "watch_threshold": WATCH, "drift_threshold": DRIFT,
                   "threshold_note": "Illustrative review thresholds, not statistically calibrated or operator-approved."},
        "features": rows, "summary": {"statuses": statuses, "quality_cells": quality, "human_review_recommended": needs_review},
        "action": "Human review only. No automatic retraining, policy change, approval or money movement.",
        "limitations": ["Input distribution shift is not proof of model accuracy loss or fraud.",
                        "Pooled periods can differ because of seasonality or agent mix; investigate before acting.",
                        "Quality counts are feature cells, not unique agents or transactions; warm-up excluded.",
                        "No live telemetry, missing-hour/freshness detection, subgroup drift or automatic alerts.",
                        "Only selected input features are checked; future labels are never monitored or used for binning."],
    }
