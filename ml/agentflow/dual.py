"""Dual-liquidity intelligence (Phase 1): e-float pressure fields, a deterministic
liquidity state, evidence-based explanations and held-out validation.

Domain fact: an MFS agent manages two coupled resources. Physical cash supports cash-out,
e-float supports cash-in, and each transaction shifts value from one side to the other.

Scope of Phase 1
----------------
* Forecasts the e-float requirement and reports e-float *pressure* next to the existing
  cash risk. It does not change the cash risk score, the V1/V2 rebalancing policies or the
  cash impact simulator.
* The synthetic data does not simulate declined cash-in (e-float is clipped at zero), so the
  held-out e-float label below is a *theoretical requirement-pressure* label computed from the
  requested flow, not a count of failed cash-in transactions.
* No 0-100 e-float score is invented. Pressure is stated in BDT and coverage ratios.

liquidity_state (deterministic, evaluated in this order)
--------------------------------------------------------
cash pressure   := cash risk_level in {HIGH, CRITICAL}            (existing cash engine)
e-float pressure := expected_efloat_gap > 0                         (balance < P50 requirement)

DUAL_PRESSURE    both pressures
CASH_PRESSURE    cash pressure only
EFLOAT_PRESSURE  e-float pressure only
WATCH            neither, but cash risk is MEDIUM or the e-float P90 requirement is not covered
HEALTHY          otherwise
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import config
from .risk import MIN_REQUIREMENT, bdt, bn_bdt, bn_num

LIQUIDITY_STATES = ("HEALTHY", "WATCH", "CASH_PRESSURE", "EFLOAT_PRESSURE", "DUAL_PRESSURE")
CASH_PRESSURE_LEVELS = ("HIGH", "CRITICAL")


def efloat_pressure(efloat_balance, req_p50, req_p90) -> pd.DataFrame:
    """Transparent e-float resource-pressure fields (BDT and ratios, no score)."""
    bal = np.maximum(np.asarray(efloat_balance, float), 0.0)
    p50 = np.maximum(np.asarray(req_p50, float), 0.0)
    p90 = np.maximum(np.asarray(req_p90, float), p50)
    bal, p50, p90 = np.broadcast_arrays(bal, p50, p90)
    cov = np.where(p50 >= MIN_REQUIREMENT, bal / np.maximum(p50, 1.0), np.nan)
    cov90 = np.where(p90 >= MIN_REQUIREMENT, bal / np.maximum(p90, 1.0), np.nan)
    return pd.DataFrame({
        "efloat_coverage_ratio": cov,
        "efloat_coverage_ratio_p90": cov90,
        "expected_efloat_gap": np.maximum(p50 - bal, 0.0),
        "p90_efloat_gap": np.maximum(p90 - bal, 0.0),
    })


def liquidity_state(cash_risk_level, expected_efloat_gap, p90_efloat_gap) -> np.ndarray:
    """Deterministic dual liquidity state from the cash risk level and e-float gaps."""
    lvl = np.asarray(cash_risk_level, dtype=object)
    gap = np.nan_to_num(np.asarray(expected_efloat_gap, float), nan=0.0)
    gap90 = np.nan_to_num(np.asarray(p90_efloat_gap, float), nan=0.0)
    cash_p = np.isin(lvl, CASH_PRESSURE_LEVELS)
    ef_p = gap > 0
    watch = (lvl == "MEDIUM") | (gap90 > 0)
    return np.select(
        [cash_p & ef_p, cash_p, ef_p, watch],
        ["DUAL_PRESSURE", "CASH_PRESSURE", "EFLOAT_PRESSURE", "WATCH"],
        default="HEALTHY",
    ).astype(object)


def add_dual_fields(snap: pd.DataFrame) -> pd.DataFrame:
    """Add e-float pressure fields and ``liquidity_state`` to a snapshot (in place, returned)."""
    if "pred_efloat_requirement_6h" not in snap.columns:
        return snap
    ef = efloat_pressure(snap["efloat_balance"], snap["pred_efloat_requirement_6h"],
                         snap["pred_efloat_requirement_p90_6h"])
    ef.index = snap.index
    for c in ef.columns:
        snap[c] = ef[c]
    snap["liquidity_state"] = liquidity_state(snap["risk_level"], snap["expected_efloat_gap"],
                                              snap["p90_efloat_gap"])
    return snap


def state_counts(states) -> dict:
    s = pd.Series(states)
    return {k: int((s == k).sum()) for k in LIQUIDITY_STATES}


# ---------------------------------------------------------------- explanations
def explain_state(r: dict) -> list[dict]:
    """Evidence-based English + Bangla sentences for one agent's liquidity state (no language model)."""
    state = r["liquidity_state"]
    cash, ef = float(r["cash_balance"]), float(r["efloat_balance"])
    c50, c90 = float(r["pred_net_requirement_6h"]), float(r["pred_net_requirement_p90_6h"])
    e50, e90 = float(r["pred_efloat_requirement_6h"]), float(r["pred_efloat_requirement_p90_6h"])
    cgap, egap, egap90 = float(r["expected_shortfall"]), float(r["expected_efloat_gap"]), float(r["p90_efloat_gap"])
    out: list[dict] = []

    def add(code, text, text_bn, evidence):
        out.append({"code": code, "text": text, "text_bn": text_bn,
                    "evidence": {k: round(float(v), 2) if isinstance(v, (int, float, np.floating)) else v
                                 for k, v in evidence.items()}})

    if state == "DUAL_PRESSURE":
        add("dual_pressure",
            "This agent faces pressure on both resources: physical cash may be insufficient for cash-out "
            "demand while e-float may be insufficient for cash-in demand.",
            "এই এজেন্টের দুই ধরনের তারল্যেই চাপ রয়েছে: ক্যাশ-আউটের জন্য নগদ এবং ক্যাশ-ইনের জন্য ই-ফ্লোট "
            "যথেষ্ট না-ও হতে পারে।",
            {"risk_level": r["risk_level"], "expected_shortfall": cgap, "expected_efloat_gap": egap})
    if state in ("DUAL_PRESSURE", "CASH_PRESSURE"):
        add("cash_pressure",
            f"Current cash is {bdt(cash)} while the predicted next-6h peak cash requirement is {bdt(c50)} "
            f"(P90: {bdt(c90)}). Cash risk is {r['risk_level']}; expected cash gap: {bdt(cgap)}.",
            f"বর্তমান নগদ {bn_bdt(cash)}, আগামী ৬ ঘণ্টায় সর্বোচ্চ নগদ প্রয়োজনের পূর্বাভাস {bn_bdt(c50)} "
            f"(P90: {bn_bdt(c90)})। প্রত্যাশিত নগদ ঘাটতি {bn_bdt(cgap)}।",
            {"cash_balance": cash, "pred_net_requirement_6h": c50, "pred_net_requirement_p90_6h": c90,
             "expected_shortfall": cgap, "risk_level": r["risk_level"]})
    if state in ("DUAL_PRESSURE", "EFLOAT_PRESSURE"):
        add("efloat_pressure",
            f"Current e-float is {bdt(ef)} while the predicted next-6h peak e-float requirement is {bdt(e50)} "
            f"(P90: {bdt(e90)}). Expected gap: {bdt(egap)}.",
            f"বর্তমান ই-ফ্লোট {bn_bdt(ef)}, আগামী ৬ ঘণ্টায় সর্বোচ্চ ই-ফ্লোট প্রয়োজনের পূর্বাভাস {bn_bdt(e50)} "
            f"(P90: {bn_bdt(e90)})। প্রত্যাশিত ঘাটতি {bn_bdt(egap)}।",
            {"efloat_balance": ef, "pred_efloat_requirement_6h": e50, "pred_efloat_requirement_p90_6h": e90,
             "expected_efloat_gap": egap})
    if state == "WATCH":
        if r["risk_level"] == "MEDIUM":
            add("watch_cash",
                f"Cash risk is MEDIUM: current cash {bdt(cash)} against a predicted peak requirement of {bdt(c50)} "
                f"(P90: {bdt(c90)}).",
                f"নগদ ঝুঁকি মাঝারি: বর্তমান নগদ {bn_bdt(cash)}, পূর্বাভাসিত সর্বোচ্চ প্রয়োজন {bn_bdt(c50)} "
                f"(P90: {bn_bdt(c90)})।",
                {"cash_balance": cash, "pred_net_requirement_6h": c50, "pred_net_requirement_p90_6h": c90,
                 "risk_level": r["risk_level"]})
        if egap90 > 0:
            add("watch_efloat",
                f"Expected e-float need ({bdt(e50)}) is covered by the current {bdt(ef)}, but a high-demand "
                f"(P90) scenario of {bdt(e90)} would leave a gap of {bdt(egap90)}.",
                f"প্রত্যাশিত ই-ফ্লোট প্রয়োজন ({bn_bdt(e50)}) বর্তমান {bn_bdt(ef)} দিয়ে পূরণ হয়, তবে উচ্চ-চাহিদার "
                f"(P90) পরিস্থিতিতে {bn_bdt(e90)} প্রয়োজন হলে {bn_bdt(egap90)} ঘাটতি থাকবে।",
                {"efloat_balance": ef, "pred_efloat_requirement_6h": e50, "pred_efloat_requirement_p90_6h": e90,
                 "p90_efloat_gap": egap90})
    if state == "HEALTHY":
        add("healthy",
            f"Both expected cash and e-float requirements are covered at the current decision time "
            f"(cash {bdt(cash)} vs {bdt(c50)}; e-float {bdt(ef)} vs {bdt(e50)}).",
            f"এই সময়ে প্রত্যাশিত নগদ ও ই-ফ্লোট উভয় প্রয়োজনই পূরণ হচ্ছে (নগদ {bn_bdt(cash)} বনাম {bn_bdt(c50)}; "
            f"ই-ফ্লোট {bn_bdt(ef)} বনাম {bn_bdt(e50)})।",
            {"cash_balance": cash, "pred_net_requirement_6h": c50, "efloat_balance": ef,
             "pred_efloat_requirement_6h": e50})
    return out


# ---------------------------------------------------------------- evaluation
def _binary(y: np.ndarray, alert: np.ndarray) -> dict:
    tp = int((alert & y).sum())
    fp = int((alert & ~y).sum())
    fn = int((~alert & y).sum())
    p = tp / max(tp + fp, 1)
    r = tp / max(tp + fn, 1)
    return {"alerts": int(alert.sum()), "alert_rate": float(alert.mean()), "true_positives": tp,
            "false_positives": fp, "missed": fn, "precision": p, "recall": r,
            "f1": 2 * p * r / max(p + r, 1e-9)}


def pressure_evaluation(d: pd.DataFrame, p50: np.ndarray, p90: np.ndarray) -> dict:
    """Held-out e-float pressure evaluation on decision rows ``d``.

    Label (known only in the future): efloat_balance < actual future_6h_net_efloat_demand. This is a
    theoretical requirement-pressure label from the requested flow, not a failed cash-in count.
    Signals use pre-specified thresholds, never chosen on the test set:
      expected pressure: efloat_balance < predicted P50 requirement
      cautious watch:    efloat_balance < predicted P90 requirement
    """
    bal = d["efloat_balance"].to_numpy(float)
    y = bal < d["future_6h_net_efloat_demand"].to_numpy(float)
    res = {"n_decisions": int(len(d)), "prevalence": float(y.mean()),
           "label": "efloat_balance < actual future_6h_net_efloat_demand (theoretical requirement pressure, "
                    "not observed failed cash-in)",
           "signals": {"expected_pressure_p50": {"definition": "efloat_balance < predicted P50 requirement",
                                                 **_binary(y, bal < np.asarray(p50))},
                       "cautious_watch_p90": {"definition": "efloat_balance < predicted P90 requirement",
                                              **_binary(y, bal < np.asarray(p90))}}}
    return res


def efloat_forecast_metrics(d: pd.DataFrame, p50: np.ndarray, p90: np.ndarray) -> dict:
    """ML vs naive baselines for the e-float requirement on the same rows ``d``."""
    from .forecast import BASELINES, regression_metrics
    y = d["future_6h_net_efloat_demand"].to_numpy(float)
    entry = {"target": "future_6h_net_efloat_demand", "ml_model": regression_metrics(y, p50), "baselines": {}}
    for b_name, b_col in BASELINES["efloat_requirement"].items():
        entry["baselines"][b_name] = regression_metrics(y, d[b_col].to_numpy(float))
    best = min(entry["baselines"], key=lambda k: entry["baselines"][k]["mae"])
    entry["best_baseline"] = best
    for key, ref in (("improvement_vs_best_baseline", entry["baselines"][best]),
                     ("improvement_vs_naive", entry["baselines"]["naive_yesterday"])):
        entry[key] = {"mae_pct": 100 * (1 - entry["ml_model"]["mae"] / ref["mae"]),
                      "rmse_pct": 100 * (1 - entry["ml_model"]["rmse"] / ref["rmse"])}
    entry["quantile_p90"] = {"nominal_coverage": 0.9, "empirical_coverage": float(np.mean(y <= np.asarray(p90))),
                             "mean_band_width": float(np.mean(np.asarray(p90) - np.asarray(p50)))}
    groups = {}
    for gcol in ("location_cluster", "agent_volume_segment"):
        groups[gcol] = {}
        for g in sorted(d[gcol].unique()):
            m = (d[gcol] == g).to_numpy()
            ml = regression_metrics(y[m], np.asarray(p50)[m])
            nv = regression_metrics(y[m], d.loc[m, "efloat_req_same_window_1d"].to_numpy(float))
            sv = regression_metrics(y[m], d.loc[m, "efloat_req_same_window_avg7"].to_numpy(float))
            groups[gcol][str(g)] = {"ml_mae": ml["mae"], "ml_wape": ml["wape"], "naive_mae": nv["mae"],
                                    "seasonal_mae": sv["mae"], "p90_coverage": float(np.mean(y[m] <= np.asarray(p90)[m])),
                                    "n": ml["n"]}
    entry["group_consistency"] = groups
    return entry


def evaluate_dual(test_df: pd.DataFrame, preds: pd.DataFrame, operating_hours) -> dict:
    """Held-out dual-liquidity forecast validation (written to ml/artifacts/dual_liquidity.json)."""
    p = preds.reindex(test_df.index)
    out = {"label": "Synthetic held-out evaluation - dual-liquidity forecast validation (Phase 1)",
           "test_start": str(test_df["timestamp"].min()), "test_end": str(test_df["timestamp"].max()),
           "forecast": efloat_forecast_metrics(test_df, p["pred_efloat_requirement_6h"].to_numpy(),
                                               p["pred_efloat_requirement_p90_6h"].to_numpy())}
    d = test_df[test_df["hour"].isin(operating_hours)]
    pd_ = p.loc[d.index]
    out["pressure"] = pressure_evaluation(d, pd_["pred_efloat_requirement_6h"].to_numpy(),
                                          pd_["pred_efloat_requirement_p90_6h"].to_numpy())
    out["pressure"]["rows"] = "held-out operating hours (08:00-21:00), same rows as the cash risk-alert evaluation"
    return out


def validation_check(feats: pd.DataFrame, val_start: pd.Timestamp, val_end: pd.Timestamp,
                     operating_hours, max_iter: int = 400) -> dict:
    """Training-period chronological check of the pre-specified e-float models.

    Fits on rows whose target window ends before ``val_start`` and scores ``val_start..val_end``
    (both strictly before the held-out test period). Used to record whether the fixed design beats
    the baselines *before* the test set is looked at; nothing is tuned on it.
    """
    from . import forecast
    from .features import EFLOAT_TARGET, TARGETS
    H = config.HORIZON_H
    if not (val_end < config.TEST_START):
        raise ValueError("validation window overlaps the held-out test period")
    has_hist = feats["out_same_window_avg7"].notna() & feats["out_rolling_mean_168h"].notna()
    has_target = feats[TARGETS + [EFLOAT_TARGET]].notna().all(axis=1)
    dev = feats[has_hist & has_target & (feats["timestamp"] < val_start - pd.Timedelta(hours=H))]
    val = feats[has_hist & has_target & feats["timestamp"].between(val_start, val_end)
                & (feats["timestamp"] + pd.Timedelta(hours=H) < config.TEST_START)]
    bundle = forecast.train(dev, max_iter=max_iter)
    pv = bundle.predict(val)
    res = {"dev_end": str(dev["timestamp"].max()), "val_start": str(val["timestamp"].min()),
           "val_end": str(val["timestamp"].max()), "dev_rows": int(len(dev)), "val_rows": int(len(val)),
           "forecast": efloat_forecast_metrics(val, pv["pred_efloat_requirement_6h"].to_numpy(),
                                               pv["pred_efloat_requirement_p90_6h"].to_numpy())}
    d = val[val["hour"].isin(operating_hours)]
    res["pressure"] = pressure_evaluation(d, pv.loc[d.index, "pred_efloat_requirement_6h"].to_numpy(),
                                          pv.loc[d.index, "pred_efloat_requirement_p90_6h"].to_numpy())
    del res["forecast"]["group_consistency"]
    return res
