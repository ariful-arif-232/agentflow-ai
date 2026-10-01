"""Transparent, deterministic liquidity risk engine and structured explanations.

risk_score (0-100) is the sum of five bounded, monotone components:

=================  ====  ===========================================================
component          max   definition
=================  ====  ===========================================================
coverage            45   45 * clip((1.25 - coverage) / 1.25, 0, 1),
                         coverage = cash / forecast peak net requirement (P50)
tail_risk           20   20 * clip(1 - cash / P90 requirement, 0, 1)
deficit_size        20   20 * clip(expected_shortfall / 40,000 BDT, 0, 1)
velocity            10   10 * clip(velocity_ratio_3h - 1, 0, 1)
history              5    5 * clip(historical_shortage_rate / 0.15, 0, 1)
=================  ====  ===========================================================

Levels: LOW < 25 <= MEDIUM < 50 <= HIGH < 75 <= CRITICAL.

Forecast deficit and reserve coverage dominate (up to 85 of 100 points). Holding all
other inputs fixed, less cash or a larger forecast requirement can never lower the
score (tested in tests/test_risk.py). Behavioural anomaly status is deliberately *not*
part of the liquidity score; it raises review priority instead.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

WEIGHTS = {"coverage": 45.0, "tail_risk": 20.0, "deficit_size": 20.0, "velocity": 10.0, "history": 5.0}
COVERAGE_SAFE = 1.25
DEFICIT_SCALE_BDT = 40_000.0
HISTORY_SCALE = 0.15
LEVELS = (("CRITICAL", 75.0), ("HIGH", 50.0), ("MEDIUM", 25.0), ("LOW", 0.0))
MIN_REQUIREMENT = 1_000.0  # below this the agent is treated as having no material requirement


def risk_level(score):
    score = np.asarray(score, dtype=float)
    out = np.full(score.shape, "LOW", dtype=object)
    for name, lo in reversed(LEVELS):
        out = np.where(score >= lo, name, out)
    return out


def compute_risk(cash, req_p50, req_p90, velocity_ratio=1.0, hist_shortage_rate=0.0) -> pd.DataFrame:
    """Vectorised risk computation. All inputs broadcast to arrays."""
    cash = np.maximum(np.asarray(cash, float), 0.0)
    req = np.maximum(np.asarray(req_p50, float), 0.0)
    req90 = np.maximum(np.asarray(req_p90, float), req)
    vel = np.nan_to_num(np.asarray(velocity_ratio, float), nan=1.0)
    hist = np.nan_to_num(np.asarray(hist_shortage_rate, float), nan=0.0)
    cash, req, req90, vel, hist = np.broadcast_arrays(cash, req, req90, vel, hist)

    material = req >= MIN_REQUIREMENT
    coverage = np.where(material, cash / np.maximum(req, 1.0), np.inf)
    cov90 = np.where(req90 >= MIN_REQUIREMENT, cash / np.maximum(req90, 1.0), np.inf)
    shortfall = np.maximum(req - cash, 0.0)

    comp = {
        "coverage": WEIGHTS["coverage"] * np.clip((COVERAGE_SAFE - coverage) / COVERAGE_SAFE, 0, 1),
        "tail_risk": WEIGHTS["tail_risk"] * np.clip(1.0 - cov90, 0, 1),
        "deficit_size": WEIGHTS["deficit_size"] * np.clip(shortfall / DEFICIT_SCALE_BDT, 0, 1),
        "velocity": WEIGHTS["velocity"] * np.clip(vel - 1.0, 0, 1),
        "history": WEIGHTS["history"] * np.clip(hist / HISTORY_SCALE, 0, 1),
    }
    score = np.clip(sum(comp.values()), 0, 100)
    out = pd.DataFrame({f"risk_{k}": v for k, v in comp.items()})
    out["coverage_ratio"] = np.where(np.isinf(coverage), np.nan, coverage)
    out["coverage_ratio_p90"] = np.where(np.isinf(cov90), np.nan, cov90)
    out["expected_shortfall"] = shortfall
    out["risk_score"] = np.round(score, 1)
    out["risk_level"] = risk_level(out["risk_score"].to_numpy())
    return out


def bdt(x: float) -> str:
    return f"BDT {x:,.0f}"


def explain(r: dict) -> list[dict]:
    """Structured, evidence-based reasons for one agent's risk (ordered by contribution).

    Every sentence is generated from calculated values in ``r`` - no free text model.
    """
    reasons = []
    req, req90, cash = r["pred_net_requirement_6h"], r["pred_net_requirement_p90_6h"], r["cash_balance"]
    cov = r.get("coverage_ratio")
    if req >= MIN_REQUIREMENT:
        reasons.append({
            "code": "forecast_requirement", "component": "coverage",
            "points": r["risk_coverage"],
            "text": (f"Forecast peak cash requirement for the next 6 hours is {bdt(req)} "
                     f"(90th-percentile scenario {bdt(req90)})."),
            "evidence": {"pred_net_requirement_6h": req, "pred_net_requirement_p90_6h": req90},
        })
        reasons.append({
            "code": "coverage", "component": "coverage", "points": r["risk_coverage"],
            "text": f"Current cash of {bdt(cash)} covers about {100 * cov:.0f}% of that requirement.",
            "evidence": {"cash_balance": cash, "coverage_ratio": cov},
        })
    else:
        reasons.append({"code": "no_material_requirement", "component": "coverage", "points": 0.0,
                        "text": "Forecast cash-in is expected to offset cash-out over the next 6 hours.",
                        "evidence": {"pred_net_requirement_6h": req}})
    if r["expected_shortfall"] > 0:
        reasons.append({"code": "shortfall", "component": "deficit_size", "points": r["risk_deficit_size"],
                        "text": f"Expected shortfall of {bdt(r['expected_shortfall'])} if no action is taken.",
                        "evidence": {"expected_shortfall": r["expected_shortfall"]}})
    if req90 > cash >= 0 and req90 >= MIN_REQUIREMENT and r["risk_tail_risk"] > 0:
        reasons.append({"code": "tail_risk", "component": "tail_risk", "points": r["risk_tail_risk"],
                        "text": f"In a high-demand (P90) scenario the gap widens to {bdt(req90 - cash)}.",
                        "evidence": {"p90_gap": req90 - cash}})
    vel = r.get("velocity_ratio_3h")
    if vel is not None and not np.isnan(vel) and vel > 1.05:
        reasons.append({"code": "velocity", "component": "velocity", "points": r["risk_velocity"],
                        "text": (f"Transaction velocity over the last 3 hours is {100 * (vel - 1):.0f}% above "
                                 "this agent's usual level for the same hours."),
                        "evidence": {"velocity_ratio_3h": vel}})
    hist = r.get("hist_shortage_rate", 0.0)
    if hist and hist > 0.01:
        reasons.append({"code": "history", "component": "history", "points": r["risk_history"],
                        "text": f"This agent was short of cash in {100 * hist:.1f}% of operating hours in the training period.",
                        "evidence": {"hist_shortage_rate": hist}})
    # Context (does not add points directly; explains *why* the forecast is high).
    seasonal, typical = r.get("out_same_window_avg7"), r.get("out_rolling_mean_168h")
    if seasonal and typical and typical > 0:
        uplift = seasonal / (6 * typical) - 1
        if uplift > 0.10:
            reasons.append({"code": "seasonal_window", "component": "context", "points": 0.0,
                            "text": (f"This time window historically sees {100 * uplift:.0f}% more cash-out than "
                                     "the agent's average 6-hour period."),
                            "evidence": {"same_window_avg7": seasonal, "avg_6h_window": 6 * typical}})
    if r.get("is_salary_period"):
        reasons.append({"code": "salary_period", "component": "context", "points": 0.0,
                        "text": "Salary period: cash-out demand is typically elevated around month end / start.",
                        "evidence": {"is_salary_period": True}})
    if r.get("is_market_day"):
        reasons.append({"code": "market_day", "component": "context", "points": 0.0,
                        "text": "Today is this agent's weekly market (haat) day, which historically raises demand.",
                        "evidence": {"is_market_day": True}})
    order = {"coverage": 0, "deficit_size": 1, "tail_risk": 2, "velocity": 3, "history": 4, "context": 5}
    reasons.sort(key=lambda d: (order[d["component"]], -d["points"]))
    for d in reasons:
        d["points"] = round(float(d["points"]), 1)
        d["evidence"] = {k: (round(float(v), 4) if isinstance(v, (int, float, np.floating)) and not isinstance(v, bool) else v)
                         for k, v in d["evidence"].items()}
    return reasons
