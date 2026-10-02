"""Phase 2B-0: complementarity feasibility + multi-seed robustness audit (research only, read-only).

Pre-registered protocol: docs/DUAL_COMPLEMENTARITY_PROTOCOL.md. For each pre-registered seed the
unchanged Dual World v2 (assumptions 2A.1) and its unchanged Phase 2A pipeline are run; the Phase 2A
artifacts are never overwritten (seed 2026 must reproduce them exactly). Writes
ml/artifacts_dual/complementarity_seed_2026.json and complementarity_multiseed.json.

Usage:  python ml/scripts/run_complementarity.py
"""
from __future__ import annotations

import _bootstrap  # noqa: F401

import json

import numpy as np
import pandas as pd

from agentflow import anomaly, complementarity as cp, dual_world as dw, dual_world_eval as ev, forecast
from agentflow.features import EFLOAT_TARGET

PHASE_2A_FILES = ("world_summary.json", "forecast_metrics.json", "status_quo_impact.json")


def behaviour_status(f: pd.DataFrame) -> pd.DataFrame:
    """Legacy hybrid detector fitted on this world's training period; worst score over trailing 6 h."""
    af = anomaly.anomaly_features(f)
    det = anomaly.AnomalyDetector().fit(af[f["timestamp"] < dw.TEST_START])
    sc = pd.DataFrame({"timestamp": f["timestamp"], "agent_id": f["agent_id"], "s": det.score(af)})
    mat = sc.pivot(index="timestamp", columns="agent_id", values="s").rolling(cp.ANOMALY_LOOKBACK_H, min_periods=1).max()
    st = pd.DataFrame(det.status(mat.to_numpy()), index=mat.index, columns=mat.columns)
    return st.stack().rename("behaviour_status").reset_index()


def decision_frame(f: pd.DataFrame, bundle, status: pd.DataFrame, hours) -> pd.DataFrame:
    has_hist = f["out_same_window_avg7"].notna() & f["out_rolling_mean_168h"].notna()
    rows = f[(f["timestamp"] >= dw.TEST_START) & has_hist & f["hour"].isin(hours)]
    d = rows.join(bundle.predict(rows))
    return d.merge(status, on=["timestamp", "agent_id"], how="left")


def oracle(d: pd.DataFrame, op_pairs: pd.DataFrame) -> dict:
    """EVALUATION ONLY: same pairing with actual future requirements (never used operationally)."""
    o = d[d["future_6h_net_cash_demand"].notna() & d[EFLOAT_TARGET].notna()].copy()
    for p50, p90, act in (("pred_net_requirement_6h", "pred_net_requirement_p90_6h", "future_6h_net_cash_demand"),
                          ("pred_efloat_requirement_6h", "pred_efloat_requirement_p90_6h", EFLOAT_TARGET)):
        o[p50] = o[act]
        o[p90] = o[act]
    r = cp.analyse(o)
    truth = d.set_index(["timestamp", "agent_id"])
    a_true = (truth["future_6h_net_cash_demand"] > truth["cash_balance"])
    b_true = (truth[EFLOAT_TARGET] > truth["efloat_balance"])
    if len(op_pairs):
        ka = list(zip(op_pairs["timestamp"], op_pairs["a"]))
        kb = list(zip(op_pairs["timestamp"], op_pairs["b"]))
        both = a_true.reindex(ka).fillna(False).to_numpy() & b_true.reindex(kb).fillna(False).to_numpy()
        rate = float(both.mean())
    else:
        rate = None
    return {"label": "oracle / evaluation only - uses actual future requirements; never used operationally",
            "decision_rows_with_actuals": int(len(o)), "viable_pairs": r["viable_pairs"],
            "cash_side_share_with_counterparty": r["cash_side_share_with_counterparty"],
            "efloat_side_share_with_counterparty": r["efloat_side_share_with_counterparty"],
            "greedy_swappable_bdt": r["greedy_swappable_bdt"],
            "operational_viable_pairs_truly_complementary_share": rate}


def clean(res: dict) -> dict:
    return {k: v for k, v in res.items() if not k.startswith("_")}


def appendix(d_all: pd.DataFrame) -> dict:
    out = {}
    for h, g in d_all.groupby("hour"):
        r = cp.analyse(g)
        out[str(int(h))] = {k: r[k] for k in ("cash_pressure_rows", "efloat_pressure_rows", "viable_pairs",
                                               "cash_side_share_with_counterparty", "efloat_side_share_with_counterparty",
                                               "greedy_swappable_bdt")}
    return out


def main() -> None:
    per_seed, detail_2026 = {}, None
    for seed in cp.SEEDS:
        world = dw.generate_world(seed=seed)
        arts, state = ev.run(world, model_path=dw.MODELS_DIR / f"forecast_models_dual_seed_{seed}.joblib", return_state=True)
        reproduced = None
        if seed == dw.SEED:
            reproduced = all(json.loads(json.dumps(arts[n], default=float)) == json.loads((dw.ARTIFACTS_DIR / n).read_text())
                             for n in PHASE_2A_FILES)
        f, bundle = state["features"], state["bundle"]
        status = behaviour_status(f)
        d = decision_frame(f, bundle, status, cp.DECISION_HOURS)
        res = cp.analyse(d)
        fm, sq = arts["forecast_metrics.json"]["held_out"], arts["status_quo_impact.json"]
        prev = sq["held_out_decision_time_pressure"]["prevalence"]
        row = {
            "seed": seed, "world_hash": arts["world_summary.json"]["world_hash"],
            "cash_pressure_prevalence_next6h": prev["cash"]["realised_next_6h"]["rate"],
            "efloat_pressure_prevalence_next6h": prev["efloat"]["realised_next_6h"]["rate"],
            "cash_forecast_improvement_vs_best_pct": fm["cash_requirement"]["improvement_vs_best_baseline"]["mae_pct"],
            "efloat_forecast_improvement_vs_best_pct": fm["efloat_requirement"]["improvement_vs_best_baseline"]["mae_pct"],
            "cash_p90_coverage": fm["cash_requirement"]["quantile_p90"]["empirical_coverage"],
            "efloat_p90_coverage": fm["efloat_requirement"]["quantile_p90"]["empirical_coverage"],
            "cash_pressure_rows": res["cash_pressure_rows"], "efloat_pressure_rows": res["efloat_pressure_rows"],
            "viable_pairs": res["viable_pairs"], "distinct_agents": res["distinct_agents"]["total"],
            "cash_side_share_with_counterparty": res["cash_side_share_with_counterparty"],
            "efloat_side_share_with_counterparty": res["efloat_side_share_with_counterparty"],
            "greedy_swappable_bdt": res["greedy_swappable_bdt"],
            "cash_need_coverable_pct": res["cash_need_coverable_pct"],
            "efloat_need_coverable_pct": res["efloat_need_coverable_pct"],
            "useful_districts": res["useful_districts"],
            "median_distance_km": res["median_distance_km"], "p90_distance_km": res["p90_distance_km"],
            "bar": cp.bar_check(res),
        }
        if reproduced is not None:
            row["phase_2a_artifacts_reproduced"] = reproduced
        per_seed[seed] = row
        if seed == 2026:
            d_all = decision_frame(f, bundle, status, cp.APPENDIX_HOURS)
            detail_2026 = {**clean(res), "oracle": oracle(d, res["_pairs"]), "hourly_appendix_08_21": appendix(d_all)}
        print(f"[seed {seed}] pairs={row['viable_pairs']} agents={row['distinct_agents']} "
              f"cash_share={row['cash_side_share_with_counterparty']:.3f} ef_share={row['efloat_side_share_with_counterparty']:.3f} "
              f"swappable={row['greedy_swappable_bdt']:,.0f} bar={row['bar']['passes']}"
              + (f" phase2A_reproduced={reproduced}" if reproduced is not None else ""))

    common = {"label": "Synthetic held-out simulation - Dual-Liquidity World v2 - complementarity feasibility audit (read-only)",
              "world_version": dw.WORLD_VERSION, "assumptions_version": dw.ASSUMPTIONS_VERSION,
              "protocol": "docs/DUAL_COMPLEMENTARITY_PROTOCOL.md",
              "constants": {"seeds": list(cp.SEEDS), "decision_hours": list(cp.DECISION_HOURS),
                            "max_distance_km": cp.MAX_DISTANCE_KM, "min_swap_bdt": cp.MIN_SWAP_BDT,
                            "rounding_bdt": cp.ROUNDING_BDT, "reserve": "max(5000, 1.10 x P90)", "bar": cp.BAR,
                            "min_worlds_passing": cp.MIN_WORLDS_PASSING,
                            "useful_district_min_pairs": cp.USEFUL_DISTRICT_MIN_PAIRS}}
    numeric = [k for k, v in per_seed[2026].items() if isinstance(v, (int, float)) and not isinstance(v, bool) and k != "seed"]
    summary = {k: {"mean": float(np.mean([per_seed[s][k] for s in cp.SEEDS])),
                   "median": float(np.median([per_seed[s][k] for s in cp.SEEDS])),
                   "min": float(min(per_seed[s][k] for s in cp.SEEDS)),
                   "max": float(max(per_seed[s][k] for s in cp.SEEDS))} for k in numeric}
    passing = sum(per_seed[s]["bar"]["passes"] for s in cp.SEEDS)
    multi = {**common, "per_seed": {str(s): per_seed[s] for s in cp.SEEDS}, "robustness_summary": summary,
             "seed_2026_representativeness": cp.representativeness(per_seed, 2026),
             "overall_bar": {"worlds_passing": int(passing), "required": cp.MIN_WORLDS_PASSING,
                             "passes": bool(passing >= cp.MIN_WORLDS_PASSING)}}
    forecast.write_json(dw.ARTIFACTS_DIR / "complementarity_seed_2026.json", ev._r({**common, "seed": 2026, **detail_2026}))
    forecast.write_json(dw.ARTIFACTS_DIR / "complementarity_multiseed.json", ev._r(multi))
    print("overall bar:", multi["overall_bar"], "| seed 2026:", multi["seed_2026_representativeness"]["verdict"])


if __name__ == "__main__":
    main()
