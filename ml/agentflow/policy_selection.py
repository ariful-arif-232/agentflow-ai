"""Selection of Rebalancing Policy V2 parameters WITHOUT touching the held-out test period.

Protocol (fixed before any test-period evaluation of V2)
-------------------------------------------------------
* **Policy-development data:** for each fold, forecast models are re-trained only on rows
  whose 6-hour target window ends before the fold's validation window starts.
* **Policy-validation folds** (chronological, inside the training period, no shuffling):
    - fold A: 2026-07-21 00:00 → 2026-08-03 23:00 (contains a salary period)
    - fold B: 2026-08-04 00:00 → 2026-08-17 23:00
* **Final held-out test period:** 2026-08-18 → 2026-08-31 — used only by ``evaluate.py``.

Selection rule (pre-registered)
-------------------------------
Over both folds combined, a V2 configuration is *feasible* if
  (1) it avoids >= 95% of the unmet cash demand that V1 avoids (vs. status quo), and
  (2) it causes no more donor shortage events than V1.
Among feasible configurations choose the highest unmet demand avoided per BDT 1,000 of
logistics cost (ties: fewer transfers, then grid order). If none is feasible, the default
config is kept and V2 is reported as not better.

Deployment rule (pre-registered, applied once on the held-out test period)
-------------------------------------------------------------------------
V2 becomes the dashboard default only if, on the held-out test period,
  (a) it retains >= 95% of V1's unmet-demand avoided, and
  (b) it has no more donor shortage events than V1, and
  (c) it is strictly better than V1 on at least two of: unnecessary-transfer %, donor
      shortage events, unmet demand avoided per BDT 1,000 logistics cost.
Otherwise V1 stays the default and V2 remains selectable for comparison.
"""
from __future__ import annotations

import itertools
from dataclasses import asdict, replace

import pandas as pd

from . import config, forecast, impact
from .engine import OPERATING_HOURS
from .features import FORECAST_FEATURES, TARGETS
from .rebalance_v2 import RebalanceV2Config

H = config.HORIZON_H
FOLDS = (
    {"name": "A", "val_start": pd.Timestamp("2026-07-21 00:00"), "val_end": pd.Timestamp("2026-08-03 23:00")},
    {"name": "B", "val_start": pd.Timestamp("2026-08-04 00:00"), "val_end": pd.Timestamp("2026-08-17 23:00")},
)
GRID = {
    "target_quantile_weight": (0.5, 0.75, 1.0),
    "donor_uncertainty_mult": (0.25, 0.5, 1.0),
    "min_risk_drop": (10.0, 20.0),
    "require_p50_shortfall": (False, True),
}
RETENTION_MIN = 0.95
# The pre-registered Phase-1 selection protocol ranked donors by the Phase-1 cost; keep it reproducible.
SELECTION_BASE = RebalanceV2Config(ranking_cost_model="phase1_simple")


def assert_folds_before_test(folds=FOLDS) -> None:
    for f in folds:
        if not (f["val_start"] < f["val_end"] < config.TEST_START):
            raise ValueError(f"policy-validation fold {f['name']} overlaps the held-out test period")


def grid_configs() -> list[RebalanceV2Config]:
    keys = list(GRID)
    return [replace(SELECTION_BASE, **dict(zip(keys, vals))) for vals in itertools.product(*(GRID[k] for k in keys))]


def _fold_inputs(feats: pd.DataFrame, fold: dict, max_iter: int = 400):
    """Out-of-sample forecasts for the validation window from a model trained on earlier data only."""
    has_hist = feats["out_same_window_avg7"].notna() & feats["out_rolling_mean_168h"].notna()
    has_target = feats[TARGETS].notna().all(axis=1)
    dev = feats[has_hist & has_target & (feats["timestamp"] < fold["val_start"] - pd.Timedelta(hours=H))]
    bundle = forecast.train(dev, max_iter=max_iter)
    window = feats["timestamp"].between(fold["val_start"], fold["val_end"]) & has_hist
    preds = bundle.predict(feats.loc[window, FORECAST_FEATURES])
    hist_src = feats[(feats["timestamp"] < fold["val_start"]) & feats["hour"].isin(OPERATING_HOURS)]
    hist_rate = hist_src.groupby("agent_id")["liquidity_shortage"].mean()
    return preds, hist_rate, {"dev_rows": int(len(dev)), "dev_end": str(dev["timestamp"].max())}


def _metrics(sim: dict, base_sim: dict) -> dict:
    m = impact.summarize(sim, base_sim["unmet"])
    m["unmet_avoided_bdt"] = float(base_sim["unmet"].sum() - sim["unmet"].sum())
    m["unnecessary_transfers"] = int(round(m.get("unnecessary_interventions_pct", 0.0) * m["interventions"] / 100))
    m.setdefault("donor_shortage_events_after_transfer", 0)
    return m


def _combine(per_fold: list[dict]) -> dict:
    keys = ("unmet_avoided_bdt", "interventions", "estimated_logistics_cost_bdt", "donor_shortage_events_after_transfer",
            "unnecessary_transfers", "shortage_events")
    tot = {k: float(sum(f[k] for f in per_fold)) for k in keys}
    tot["unmet_avoided_per_1000_cost_bdt"] = 1000 * tot["unmet_avoided_bdt"] / max(tot["estimated_logistics_cost_bdt"], 1.0)
    tot["unnecessary_interventions_pct"] = 100 * tot["unnecessary_transfers"] / max(tot["interventions"], 1.0)
    return tot


def select(feats: pd.DataFrame, agents: pd.DataFrame, anomaly_status: pd.DataFrame | None,
           configs: list[RebalanceV2Config] | None = None, folds=FOLDS, max_iter: int = 400) -> dict:
    assert_folds_before_test(folds)
    configs = configs or grid_configs()
    fold_reports, v1_folds, v2_folds = [], [], {i: [] for i in range(len(configs))}
    for fold in folds:
        preds, hist_rate, info = _fold_inputs(feats, fold, max_iter)
        kw = dict(start=fold["val_start"], end=fold["val_end"])
        base = impact.simulate_policy(feats, agents, None, hist_rate, forecast_source="none", **kw)
        v1 = _metrics(impact.simulate_policy(feats, agents, preds, hist_rate, anomaly_status, "ml", policy="v1", **kw), base)
        v1_folds.append(v1)
        for i, cfg in enumerate(configs):
            sim = impact.simulate_policy(feats, agents, preds, hist_rate, anomaly_status, "ml", policy="v2",
                                         policy_cfg=cfg, **kw)
            v2_folds[i].append(_metrics(sim, base))
        fold_reports.append({"name": fold["name"], "val_start": str(fold["val_start"]), "val_end": str(fold["val_end"]),
                             **info, "status_quo_unmet_bdt": float(base["unmet"].sum()), "v1": v1})
    v1_tot = _combine(v1_folds)
    rows = []
    for i, cfg in enumerate(configs):
        tot = _combine(v2_folds[i])
        retention = tot["unmet_avoided_bdt"] / max(v1_tot["unmet_avoided_bdt"], 1.0)
        feasible = retention >= RETENTION_MIN and tot["donor_shortage_events_after_transfer"] <= v1_tot["donor_shortage_events_after_transfer"]
        rows.append({"grid_index": i, "params": {k: getattr(cfg, k) for k in RebalanceV2Config.tunable_fields()},
                     "retention_vs_v1": retention, "feasible": bool(feasible), **tot})
    feasible = [r for r in rows if r["feasible"]]
    if feasible:
        best = max(feasible, key=lambda r: (r["unmet_avoided_per_1000_cost_bdt"], -r["interventions"], -r["grid_index"]))
        chosen = replace(SELECTION_BASE, **best["params"])
        outcome = "feasible configuration selected"
    else:
        best, chosen, outcome = None, SELECTION_BASE, "no feasible configuration — default kept, V2 not better on validation"
    return {
        "label": "Policy selection on training-period validation folds (held-out test period not used)",
        "protocol": {"folds": [{k: str(v) for k, v in f.items()} for f in folds], "test_start": str(config.TEST_START),
                     "grid": {k: list(v) for k, v in GRID.items()}, "retention_min": RETENTION_MIN,
                     "selection_rule": ("feasible = retains >=95% of V1 unmet-demand avoided and no more donor shortage "
                                        "events than V1 (both folds combined); choose max unmet avoided per BDT 1,000 "
                                        "logistics cost; ties -> fewer transfers")},
        "folds": fold_reports,
        "v1_validation_total": v1_tot,
        "grid_results": rows,
        "outcome": outcome,
        "selected_grid_index": best["grid_index"] if best else None,
        "selected_config": asdict(chosen),
    }


def deployment_decision(v1: dict, v2: dict) -> dict:
    """Pre-registered rule applied to held-out results (dicts from impact.summarize + efficiency)."""
    retention = v2["unmet_avoided_bdt"] / max(v1["unmet_avoided_bdt"], 1.0)
    better = {
        "unnecessary_interventions_pct": v2.get("unnecessary_interventions_pct", 0) < v1.get("unnecessary_interventions_pct", 0),
        "donor_shortage_events_after_transfer": v2.get("donor_shortage_events_after_transfer", 0) < v1.get("donor_shortage_events_after_transfer", 0),
        "unmet_avoided_per_1000_cost_bdt": v2["unmet_avoided_per_1000_cost_bdt"] > v1["unmet_avoided_per_1000_cost_bdt"],
    }
    checks = {
        "retains_95pct_of_v1_unmet_avoided": retention >= RETENTION_MIN,
        "donor_events_not_worse": v2.get("donor_shortage_events_after_transfer", 0) <= v1.get("donor_shortage_events_after_transfer", 0),
        "strictly_better_on_at_least_two": sum(better.values()) >= 2,
    }
    adopt = all(checks.values())
    return {"rule": ("V2 default iff retains >=95% of V1 unmet-demand avoided, donor shortage events <= V1, and strictly "
                     "better on >=2 of {unnecessary %, donor events, unmet avoided per BDT 1,000 cost}"),
            "retention_vs_v1": retention, "strictly_better": better, "checks": checks,
            "default_policy": "v2" if adopt else "v1"}


def efficiency(m: dict, sq: dict) -> dict:
    avoided = sq["unmet_cash_demand_bdt"] - m["unmet_cash_demand_bdt"]
    events_avoided = sq["shortage_events"] - m["shortage_events"]
    n = m.get("interventions", 0)
    cost = m.get("estimated_logistics_cost_bdt", 0.0)
    return {"unmet_avoided_bdt": float(avoided),
            "unmet_avoided_per_transfer_bdt": float(avoided / n) if n else None,
            "unmet_avoided_per_1000_cost_bdt": float(1000 * avoided / cost) if cost else None,
            "shortage_events_avoided_per_100_transfers": float(100 * events_avoided / n) if n else None}


def summary_table(rows: list[dict], top: int = 10) -> pd.DataFrame:
    df = pd.DataFrame([{**r["params"], **{k: r[k] for k in ("retention_vs_v1", "feasible", "interventions",
                                                                 "donor_shortage_events_after_transfer",
                                                                 "unnecessary_interventions_pct",
                                                                 "unmet_avoided_per_1000_cost_bdt")}} for r in rows])
    return df.sort_values(["feasible", "unmet_avoided_per_1000_cost_bdt"], ascending=False).head(top)
