"""AgentFlow service layer: wraps the ML decision engine for the API.

The engine (data, features, models, anomaly scores) is loaded once at start-up.
Snapshots are cached per decision timestamp. Nothing here mutates source data:
approvals only run simulations, which are recorded in an in-memory audit log.
"""
from __future__ import annotations

import json
import math
import os
import sys
import threading
import uuid
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "ml"))

from agentflow import business_impact, config, engine, logistics, rebalance, rebalance_v2, risk  # noqa: E402

from .audit import fingerprint, get_audit_chain  # noqa: E402
from agentflow.engine import DEFAULT_AS_OF  # noqa: E402

DATA_LABEL = "Synthetic data for hackathon prototyping — not production upay data"


def clean(obj):
    """Recursively convert numpy / pandas scalars to JSON-safe Python values (NaN -> None)."""
    if isinstance(obj, dict):
        return {str(k): clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [clean(v) for v in obj]
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating, float)):
        v = float(obj)
        return None if math.isnan(v) or math.isinf(v) else v
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    if isinstance(obj, (pd.Timestamp, datetime)):
        return None if pd.isna(obj) else obj.isoformat()
    if obj is pd.NaT:
        return None
    return obj


def ensure_artifacts() -> None:
    """Generate data and train models if they are missing (fresh clone / deployment)."""
    from agentflow import anomaly, forecast
    if config.DATASET_PATH.exists() and forecast.MODEL_PATH.exists() and anomaly.MODEL_PATH.exists():
        return
    import runpy
    scripts = ROOT / "ml" / "scripts"
    sys.path.insert(0, str(scripts))
    if not config.DATASET_PATH.exists():
        runpy.run_path(str(scripts / "generate_data.py"), run_name="__main__")
    runpy.run_path(str(scripts / "train.py"), run_name="__main__")


AGENT_LIST_FIELDS = [
    "agent_id", "district", "location_cluster", "agent_type", "agent_volume_segment",
    "cash_balance", "pred_cash_demand_6h", "pred_net_requirement_6h", "pred_net_requirement_p90_6h",
    "expected_shortfall", "expected_surplus", "coverage_ratio", "risk_score", "risk_level",
    "anomaly_status", "anomaly_score", "review_priority", "synthetic_latitude", "synthetic_longitude",
]


class AgentFlowService:
    def __init__(self) -> None:
        ensure_artifacts()
        self.engine = engine.Engine.load(serving=True).compact()
        env_as_of = os.getenv("AGENTFLOW_AS_OF", "").strip()
        self.default_as_of = pd.Timestamp(env_as_of) if env_as_of else DEFAULT_AS_OF
        ts = self.engine.timestamps
        # Decision times offered in the UI: held-out period, where history + forecasts exist.
        self.available_as_of = [t for t in ts if t >= config.TEST_START and 6 <= t.hour <= 21]
        self._lock = threading.Lock()
        self.audit = get_audit_chain()  # shared, hash-chained (tamper-evident) simulation audit
        self._snap_cache: dict = {}
        self._plan_cache: dict = {}
        self.metrics = self._read_json("metrics.json")
        self.impact = self._read_json("impact.json")
        # Phase-2 business layer (synthetic simulated estimate); re-priced with any env rate overrides.
        biz = self._read_json("business_impact.json")
        self.business_impact = business_impact.reprice(biz, business_impact.assumptions_from_env()) if biz else {}
        # Phase-2 integration & scale evidence (synthetic benchmark; produced by ml/scripts/integration_scale.py).
        self.integration_scale = self._read_json("integration_scale.json")
        # Phase-2 targeted ML experiment (pre-registered; produced by ml/scripts/ml_experiment.py).
        self.ml_experiment = self._read_json("ml_experiment.json")
        # Default rebalancing policy comes from the pre-registered held-out deployment rule.
        self.default_policy = self.impact.get("deployment_decision", {}).get("default_policy", "v1")
        self.v2_cfg = rebalance_v2.selected_config()
        self.training = self._read_json("training_metadata.json")
        self.dataset = self._read_json("dataset_summary.json")

    @staticmethod
    def _read_json(name: str) -> dict:
        p = config.ARTIFACTS_DIR / name
        return json.loads(p.read_text()) if p.exists() else {}

    # ---------------------------------------------------------------- helpers
    def resolve_as_of(self, as_of: str | None) -> pd.Timestamp:
        if not as_of:
            return self.default_as_of
        try:
            ts = pd.Timestamp(as_of).floor("h")
        except (ValueError, TypeError):
            raise ValueError("as_of must be an ISO-8601 timestamp")
        if ts.tzinfo is not None:
            ts = ts.tz_convert(None)
        if ts not in set(self.available_as_of):
            raise ValueError(f"as_of must be an hour between {self.available_as_of[0]} and "
                             f"{self.available_as_of[-1]} (06:00-21:00)")
        return ts

    def snapshot(self, as_of: pd.Timestamp) -> pd.DataFrame:
        with self._lock:
            if as_of not in self._snap_cache:
                if len(self._snap_cache) > 64:
                    self._snap_cache.clear()
                    self._plan_cache.clear()
                self._snap_cache[as_of] = self.engine.snapshot(as_of)
            return self._snap_cache[as_of]

    def resolve_policy(self, policy: str | None) -> str:
        policy = policy or self.default_policy
        if policy not in ("v1", "v2"):
            raise ValueError("policy must be 'v1' or 'v2'")
        return policy

    def plan(self, as_of: pd.Timestamp, policy: str | None = None) -> dict:
        policy = self.resolve_policy(policy)
        snap = self.snapshot(as_of)
        with self._lock:
            key = (as_of, policy)
            if key not in self._plan_cache:
                plan = rebalance.recommend(snap) if policy == "v1" else rebalance_v2.recommend_v2(snap, self.v2_cfg)
                plan["summary"]["policy"] = policy
                self._plan_cache[key] = plan
            return self._plan_cache[key]

    def meta(self, as_of: pd.Timestamp) -> dict:
        return {"as_of": as_of.isoformat(), "data_label": DATA_LABEL, "currency": config.CURRENCY,
                "horizon_hours": config.HORIZON_H}

    # ---------------------------------------------------------------- endpoints
    def health(self) -> dict:
        return {"status": "ok", "models_loaded": True, "agents": int(len(self.engine.agents)),
                "default_as_of": self.default_as_of.isoformat(), "data_label": DATA_LABEL}

    def time_options(self) -> dict:
        return {"default_as_of": self.default_as_of.isoformat(),
                "available": [t.isoformat() for t in self.available_as_of]}

    def overview(self, as_of: pd.Timestamp) -> dict:
        snap = self.snapshot(as_of)
        plan = self.plan(as_of)
        levels = snap["risk_level"].value_counts()
        covered = snap["coverage_ratio"].isna() | (snap["coverage_ratio"] >= 1.0)
        delta = rebalance.transfers_to_cash_delta(plan["recommendations"])
        after_cash = snap.set_index("agent_id")["cash_balance"].add(pd.Series(delta), fill_value=0)
        after = self.engine.snapshot(as_of, cash_override=after_cash) if delta else snap
        covered_after = after["coverage_ratio"].isna() | (after["coverage_ratio"] >= 1.0)
        top = snap.sort_values(["risk_score", "expected_shortfall"], ascending=False).head(8)
        trend = self.network_trend(as_of)
        by_district = (snap.groupby("district")
                       .agg(agents=("agent_id", "count"),
                            at_risk=("risk_level", lambda s: int(s.isin(["HIGH", "CRITICAL"]).sum())),
                            expected_shortfall=("expected_shortfall", "sum"),
                            forecast_demand=("pred_cash_demand_6h", "sum"))
                       .reset_index().sort_values("at_risk", ascending=False))
        return clean({
            **self.meta(as_of),
            "kpis": {
                "active_agents": int(len(snap)),
                "at_risk_agents": int(levels.get("HIGH", 0) + levels.get("CRITICAL", 0)),
                "critical_agents": int(levels.get("CRITICAL", 0)),
                "medium_risk_agents": int(levels.get("MEDIUM", 0)),
                "anomaly_watch_agents": int((snap["anomaly_status"] != "NORMAL").sum()),
                "projected_service_availability_pct": float(100 * covered.mean()),
                "projected_service_availability_after_plan_pct": float(100 * covered_after.mean()),
                "forecast_cash_demand_6h": float(snap["pred_cash_demand_6h"].sum()),
                "forecast_net_requirement_6h": float(snap["pred_net_requirement_6h"].sum()),
                "total_expected_shortfall": float(snap["expected_shortfall"].sum()),
                "recommended_rebalancing_value": plan["summary"]["total_recommended_amount"],
                "n_recommendations": plan["summary"]["n_recommendations"],
                "rebalancing_policy": self.default_policy,
                "escalated_amount": plan["summary"]["escalated_amount"],
            },
            "kpi_definitions": {
                "projected_service_availability_pct": ("Share of agents whose current cash covers their forecast "
                                                       "6-hour peak cash requirement (coverage >= 100%)."),
                "at_risk_agents": "Agents with liquidity risk level HIGH or CRITICAL.",
                "forecast_cash_demand_6h": "Sum of ML-forecast requested cash-out over the next 6 hours.",
            },
            "risk_distribution": [{"level": lvl, "count": int(levels.get(lvl, 0))}
                                  for lvl in ("LOW", "MEDIUM", "HIGH", "CRITICAL")],
            "top_at_risk": top[AGENT_LIST_FIELDS].to_dict("records"),
            "urgent_recommendations": plan["recommendations"][:5],
            "demand_trend": trend,
            "districts": by_district.to_dict("records"),
        })

    def network_trend(self, as_of: pd.Timestamp, hours: int = 48) -> list[dict]:
        f = self.engine.feats
        m = f["timestamp"].between(as_of - pd.Timedelta(hours=hours - 1), as_of)
        sub = f.loc[m, ["timestamp", "cash_out_amount", "cash_in_amount", "unmet_cash_out", "future_6h_cash_demand"]]
        sub = sub.join(self.engine.preds[["pred_cash_demand_6h"]], how="left")
        g = sub.groupby("timestamp").agg(cash_out=("cash_out_amount", "sum"), cash_in=("cash_in_amount", "sum"),
                                         unmet=("unmet_cash_out", "sum"),
                                         forecast_6h=("pred_cash_demand_6h", "sum"),
                                         actual_6h=("future_6h_cash_demand", "sum")).reset_index()
        known = g["timestamp"] + pd.Timedelta(hours=config.HORIZON_H) <= as_of
        g.loc[~known, "actual_6h"] = np.nan  # not yet observable at as_of
        return g.to_dict("records")

    def agents(self, as_of, risk_level=None, district=None, cluster=None, segment=None,
               anomaly_status=None, search=None, sort="risk_score", order="desc") -> dict:
        snap = self.snapshot(as_of)
        df = snap[AGENT_LIST_FIELDS]
        if risk_level:
            df = df[df["risk_level"].isin(risk_level)]
        if district:
            df = df[df["district"] == district]
        if cluster:
            df = df[df["location_cluster"] == cluster]
        if segment:
            df = df[df["agent_volume_segment"] == segment]
        if anomaly_status:
            df = df[df["anomaly_status"].isin(anomaly_status)]
        if search:
            df = df[df["agent_id"].str.contains(search.strip().upper(), regex=False)]
        df = df.sort_values(sort, ascending=(order == "asc"), na_position="last")
        return clean({**self.meta(as_of), "count": int(len(df)), "agents": df.to_dict("records"),
                      "filters": {"districts": sorted(snap["district"].unique()),
                                  "clusters": sorted(snap["location_cluster"].unique()),
                                  "segments": ["low", "medium", "high"]}})

    def _agent_row(self, as_of, agent_id: str) -> pd.Series:
        snap = self.snapshot(as_of)
        m = snap["agent_id"] == agent_id
        if not m.any():
            raise KeyError(agent_id)
        return snap[m].iloc[0]

    def agent_detail(self, as_of, agent_id: str) -> dict:
        row = self._agent_row(as_of, agent_id)
        r = row.to_dict()
        plan = self.plan(as_of)
        as_dest = [x for x in plan["recommendations"] if x["destination_agent"] == agent_id]
        as_src = [x for x in plan["recommendations"] if x["source_agent"] == agent_id]
        esc = [x for x in plan["escalations"] if x["agent_id"] == agent_id]
        held = [x for x in plan["held_for_review"] if x["agent_id"] == agent_id]
        if as_dest:
            action = {"type": "RECEIVE_REBALANCING",
                      "summary": (f"Rebalance {risk.bdt(sum(x['recommended_amount'] for x in as_dest))} from "
                                  f"{', '.join(x['source_agent'] for x in as_dest)} (recommendation "
                                  f"{', '.join(x['id'] for x in as_dest)}).")}
        elif held:
            action = {"type": "MANUAL_REVIEW", "summary": held[0]["reason"]}
        elif esc:
            action = {"type": "ESCALATE", "summary": f"{esc[0]['reason']} Unresolved need {risk.bdt(esc[0]['unresolved_need'])}."}
        elif as_src:
            action = {"type": "DONOR", "summary": (f"Safe surplus donor: can provide "
                                                   f"{risk.bdt(sum(x['recommended_amount'] for x in as_src))} while "
                                                   f"staying above its protected level.")}
        elif r["risk_level"] == "MEDIUM":
            action = {"type": "MONITOR", "summary": "Monitor: coverage is below the comfort level; re-check next cycle."}
        else:
            action = {"type": "NONE", "summary": "No action needed: current cash covers the forecast requirement."}
        anomaly_drivers = []
        if r["anomaly_status"] != "NORMAL" and pd.notna(r["anomaly_peak_time"]):
            anomaly_drivers = self.engine.anomaly_drivers(agent_id, pd.Timestamp(r["anomaly_peak_time"]))
        hist = self.engine.agent_history(agent_id, as_of, hours=72)
        agent_static = self.engine.agents.set_index("agent_id").loc[agent_id]
        fm = self.metrics.get("forecast", {}).get("targets", {})
        return clean({
            **self.meta(as_of),
            "agent": {k: r[k] for k in ("agent_id", "district", "location_cluster", "agent_type",
                                        "agent_volume_segment", "synthetic_latitude", "synthetic_longitude")},
            "liquidity": {"cash_balance": r["cash_balance"], "efloat_balance": r["efloat_balance"],
                          "morning_target_cash": float(agent_static["target_cash_level"]),
                          "cash_out_last_6h": r["out_sum_6h"]},
            "forecast": {"pred_cash_demand_6h": r["pred_cash_demand_6h"],
                         "pred_net_requirement_6h": r["pred_net_requirement_6h"],
                         "pred_net_requirement_p90_6h": r["pred_net_requirement_p90_6h"],
                         "expected_shortfall": r["expected_shortfall"], "expected_surplus": r["expected_surplus"],
                         "seasonal_same_window_avg7": r["out_same_window_avg7"],
                         "source": "ML forecast (HistGradientBoosting) — model prediction"},
            "risk": {"risk_score": r["risk_score"], "risk_level": r["risk_level"],
                     "coverage_ratio": r["coverage_ratio"], "coverage_ratio_p90": r["coverage_ratio_p90"],
                     "components": {k: r[f"risk_{k}"] for k in risk.WEIGHTS},
                     "component_max": risk.WEIGHTS,
                     "source": "Deterministic risk engine — transparent formula"},
            "explanation": risk.explain(r),
            "anomaly": {"status": r["anomaly_status"], "score": r["anomaly_score"],
                        "peak_time": r["anomaly_peak_time"], "drivers": anomaly_drivers,
                        "note": "Behavioural anomaly = unusual activity vs. this agent's own history. "
                                "It is not a fraud determination; manual review is recommended."},
            "review_priority": r["review_priority"],
            "recommended_action": action,
            "recommendations": {"as_destination": as_dest, "as_source": as_src, "escalation": esc, "held": held},
            "history": hist.to_dict("records"),
            "model_context": {
                "cash_demand_mae_ml": fm.get("cash_demand", {}).get("ml_model", {}).get("mae"),
                "cash_demand_mae_naive": fm.get("cash_demand", {}).get("baselines", {}).get("naive_yesterday", {}).get("mae"),
                "net_requirement_mae_ml": fm.get("net_requirement", {}).get("ml_model", {}).get("mae"),
                "p90_coverage": self.metrics.get("forecast", {}).get("quantile_p90", {}).get("empirical_coverage"),
            },
        })

    def agent_forecast(self, as_of, agent_id: str) -> dict:
        row = self._agent_row(as_of, agent_id)
        hist = self.engine.agent_history(agent_id, as_of, hours=72)
        return clean({**self.meta(as_of), "agent_id": agent_id,
                      "forecast": {k: row[k] for k in ("pred_cash_demand_6h", "pred_net_requirement_6h",
                                                       "pred_net_requirement_p90_6h")},
                      "history": hist.to_dict("records")})

    def recommendations(self, as_of, policy: str | None = None) -> dict:
        policy = self.resolve_policy(policy)
        return clean({**self.meta(as_of), **self.plan(as_of, policy), "policy": policy,
                      "default_policy": self.default_policy, "available_policies": ["v2", "v1"],
                      "simulation_only": True})

    @property
    def audit_log(self) -> list[dict]:
        return self.audit.entries("intraday_rebalancing")

    def logistics_assumptions(self) -> dict:
        return clean({**logistics.describe(), "v2_ranking_cost_model": self.v2_cfg.ranking_cost_model,
                      "simulation_only": True,
                      "note": "Illustrative assumptions for a synthetic prototype. No money is moved and no "
                              "operator rate is measured."})

    def simulate(self, as_of, ids: list[str], reviewer_note: str | None, policy: str | None = None) -> dict:
        policy = self.resolve_policy(policy)
        plan = self.plan(as_of, policy)
        by_id = {r["id"]: r for r in plan["recommendations"]}
        unknown = [i for i in ids if i not in by_id]
        if unknown:
            raise LookupError(f"Unknown recommendation id(s): {', '.join(unknown)}")
        chosen = [by_id[i] for i in ids]
        snap = self.snapshot(as_of)
        delta = rebalance.transfers_to_cash_delta(chosen)
        before = snap.set_index("agent_id")
        after_cash = before["cash_balance"].add(pd.Series(delta), fill_value=0)
        after = self.engine.snapshot(as_of, cash_override=after_cash).set_index("agent_id")
        affected = sorted(delta)
        agents_out = [{
            "agent_id": a, "role": "destination" if delta[a] > 0 else "source",
            "cash_before": before.loc[a, "cash_balance"], "cash_after": after.loc[a, "cash_balance"],
            "risk_score_before": before.loc[a, "risk_score"], "risk_score_after": after.loc[a, "risk_score"],
            "risk_level_before": before.loc[a, "risk_level"], "risk_level_after": after.loc[a, "risk_level"],
            "coverage_before": before.loc[a, "coverage_ratio"], "coverage_after": after.loc[a, "coverage_ratio"],
        } for a in affected]

        def portfolio(df):
            cov = df["coverage_ratio"].isna() | (df["coverage_ratio"] >= 1.0)
            return {"at_risk_agents": int(df["risk_level"].isin(["HIGH", "CRITICAL"]).sum()),
                    "critical_agents": int((df["risk_level"] == "CRITICAL").sum()),
                    "total_expected_shortfall": float(df["expected_shortfall"].sum()),
                    "projected_service_availability_pct": float(100 * cov.mean())}

        fields = {"simulation_id": f"SIM-{uuid.uuid4().hex[:8].upper()}",
                  "created_at": datetime.now(timezone.utc).isoformat(), "as_of": as_of.isoformat(),
                  "recommendation_ids": ids, "policy": policy,
                  "total_amount": float(sum(r["recommended_amount"] for r in chosen)),
                  "logistics_cost_proxy_bdt": round(sum(r["logistics_cost"]["total_estimated_cost_bdt"] for r in chosen), 2),
                  "logistics_assumption_label": logistics.ASSUMPTION_LABEL,
                  "reviewer_acknowledged": True,
                  "reviewer_note": reviewer_note, "status": "SIMULATED — no money moved"}
        # Replay guard: the same approval (same decision time, policy and recommendations) is recorded once.
        fp = fingerprint({"kind": "intraday_rebalancing", "as_of": as_of.isoformat(), "policy": policy,
                          "recommendation_ids": sorted(ids)})
        entry, created = self.audit.append("intraday_rebalancing", fields, fp)
        return clean({**self.meta(as_of), **entry, "simulation_only": True, "replayed": not created,
                      "audit_note": ("Recorded in the tamper-evident simulation audit log." if created else
                                     "Duplicate approval: the original audit record is returned and no new record "
                                     "was written."),
                      "agents": agents_out, "portfolio_before": portfolio(before),
                      "portfolio_after": portfolio(after)})

    def scenario(self, as_of, demand_shock_pct: float, district: str | None, regional_shock_pct: float) -> dict:
        snap0 = self.snapshot(as_of)
        mult = pd.Series(1.0 + demand_shock_pct / 100.0, index=snap0["agent_id"])
        if district:
            mult[snap0.set_index("agent_id")["district"] == district] *= 1.0 + regional_shock_pct / 100.0
        snap = self.engine.snapshot(as_of, demand_multiplier=mult)
        plan = (rebalance.recommend(snap, with_details=False) if self.default_policy == "v1"
                else rebalance_v2.recommend_v2(snap, self.v2_cfg, with_details=False))

        def summary(s, p):
            cov = s["coverage_ratio"].isna() | (s["coverage_ratio"] >= 1.0)
            lv = s["risk_level"].value_counts()
            return {"risk_distribution": {k: int(lv.get(k, 0)) for k in ("LOW", "MEDIUM", "HIGH", "CRITICAL")},
                    "at_risk_agents": int(lv.get("HIGH", 0) + lv.get("CRITICAL", 0)),
                    "total_expected_shortfall": float(s["expected_shortfall"].sum()),
                    "projected_service_availability_pct": float(100 * cov.mean()),
                    "recommended_rebalancing_value": p["summary"]["total_recommended_amount"],
                    "n_recommendations": p["summary"]["n_recommendations"],
                    "escalated_amount": p["summary"]["escalated_amount"]}
        return clean({**self.meta(as_of), "inputs": {"demand_shock_pct": demand_shock_pct, "district": district,
                                                     "regional_shock_pct": regional_shock_pct},
                      "baseline": summary(snap0, self.plan(as_of)), "scenario": summary(snap, plan),
                      "note": "Scenario scales ML demand forecasts; risk and rebalancing are recomputed by the same engine."})


@lru_cache(maxsize=1)
def get_service() -> AgentFlowService:
    return AgentFlowService()
