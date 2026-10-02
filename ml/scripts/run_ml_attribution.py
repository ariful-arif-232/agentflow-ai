"""Phase 2D: ML attribution baseline audit for morning prepositioning (research only).

Pre-registered protocol: docs/ML_ATTRIBUTION_PROTOCOL.md. Compares status quo, two simple non-ML
baselines and the unchanged Phase 2C ML policy (plus evaluation-only oracles) on the same budgets,
floors, allocator and held-out demand. Writes ml/artifacts_dual/ml_attribution_seed_2026.json and
ml_attribution_multiseed.json; earlier artifacts are never overwritten.

Usage:  python ml/scripts/run_ml_attribution.py
"""
from __future__ import annotations

import _bootstrap  # noqa: F401

import json

import numpy as np
import pandas as pd

from agentflow import dual_world as dw, dual_world_eval as ev, forecast, ml_attribution as ma, prepositioning as pp
from agentflow.features import EFLOAT_TARGET

ORACLE_LABEL = "ORACLE - evaluation only, impossible operationally"
PHASE_2A_FILES = ("world_summary.json", "forecast_metrics.json", "status_quo_impact.json")
GROUPS = ("location_cluster", "agent_volume_segment")


def pivots(world: dw.DualWorld):
    h = world.hourly
    piv = lambda c: h.pivot(index="timestamp", columns="agent_id", values=c).sort_index(axis=1)  # noqa: E731
    return {c: piv(c) for c in ("requested_cash_out", "requested_cash_in", "cash_balance", "efloat_balance",
                                "unmet_cash_out", "unmet_cash_in")}


def run_seed(seed: int, phase2c: dict) -> dict:
    world = dw.generate_world(seed=seed)
    arts, state = ev.run(world, model_path=dw.MODELS_DIR / f"forecast_models_dual_seed_{seed}.joblib", return_state=True)
    reproduced = None
    if seed == dw.SEED:
        reproduced = all(json.loads(json.dumps(arts[n], default=float)) == json.loads((dw.ARTIFACTS_DIR / n).read_text())
                         for n in PHASE_2A_FILES)
    f, bundle = state["features"], state["bundle"]
    agents = world.agents.sort_values("agent_id").reset_index(drop=True)
    ids = list(agents["agent_id"])
    P = pivots(world)
    assert list(P["requested_cash_out"].columns) == ids
    hours_all = P["requested_cash_out"].index
    ro_all, ri_all = P["requested_cash_out"].to_numpy(), P["requested_cash_in"].to_numpy()
    w = np.asarray(hours_all >= dw.TEST_START)
    hours, ro, ri = hours_all[w], ro_all[w], ri_all[w]
    t0 = np.where(w)[0][0] - 1
    c0, e0 = P["cash_balance"].to_numpy()[t0], P["efloat_balance"].to_numpy()[t0]
    rec_uo, rec_ui = P["unmet_cash_out"].to_numpy()[w], P["unmet_cash_in"].to_numpy()[w]
    tc = agents["target_cash_level"].round().astype(np.int64).to_numpy()
    te = agents["target_efloat_level"].round().astype(np.int64).to_numpy()
    days = pd.date_range(dw.TEST_START, f["timestamp"].max().normalize(), freq="D")

    names = ma.OPERATIONAL_POLICIES + ma.ORACLE_POLICIES
    plans = {k: ({}, {}) for k in names}
    edges = {k: 0 for k in names}
    for d in days:
        rows = f[f["timestamp"] == d + pd.Timedelta(hours=pp.FORECAST_ROW_HOUR)].sort_values("agent_id")
        assert list(rows["agent_id"]) == ids
        pred = bundle.predict(rows)
        hs = ma.history_signals(ro_all, ri_all, hours_all, d)
        dm = np.asarray((hours >= d + pd.Timedelta(hours=8)) & (hours < d + pd.Timedelta(hours=32)))
        fc, fe = ma.peak_requirements(ro[dm], ri[dm])  # ORACLE ONLY
        signals = {
            "history_proportional": (hs["avg_daily_cash_out"], hs["avg_daily_cash_in"]),
            "seasonal_requirement_7d": (hs["avg_peak_cash_requirement"], hs["avg_peak_efloat_requirement"]),
            ma.ML_POLICY: (pred["pred_net_requirement_p90_6h"].to_numpy(), pred["pred_efloat_requirement_p90_6h"].to_numpy()),
            "oracle_6h": (rows["future_6h_net_cash_demand"].to_numpy(), rows[EFLOAT_TARGET].to_numpy()),  # ORACLE ONLY
            "oracle_full_day": (fc, fe),  # ORACLE ONLY
        }
        plans["status_quo"][0][d], plans["status_quo"][1][d] = tc, te
        for name, (cs, es) in signals.items():
            ac, ae, e = ma.allocate(agents, cs, es, ma.MODES[name])
            plans[name][0][d], plans[name][1][d] = ac, ae
            edges[name] += e

    # ---- exact conservation proof (every policy, day, district, resource)
    district = agents["district"].to_numpy()
    cons = {}
    for name, (pc, pe) in plans.items():
        mx, ok = 0, True
        for d in days:
            for p, sq in ((pc[d], tc), (pe[d], te)):
                ok &= bool((p >= 0).all()) and int(p.sum()) == int(sq.sum())
                diff = int(pd.Series(p - sq).groupby(district).sum().abs().max())
                mx = max(mx, diff)
                ok &= diff == 0
        cons[name] = {"exact": bool(ok), "max_abs_district_diff_bdt": mx}

    mask = np.asarray(hours >= dw.TEST_START + pd.Timedelta(hours=pp.DECISION_HOUR))
    sims = {k: pp.replay(ro, ri, hours, c0, e0, pc, pe) for k, (pc, pe) in plans.items()}
    fidelity = bool(np.allclose(sims["status_quo"]["unmet_out"], rec_uo) and np.allclose(sims["status_quo"]["unmet_in"], rec_ui))
    met = {k: pp.service_metrics(s, ro, ri, mask) for k, s in sims.items()}
    per_agent = {k: (s["unmet_out"][mask] + s["unmet_in"][mask]).sum(axis=0) for k, s in sims.items()}
    tol = pp.BETTER_WORSE_TOLERANCE_BDT

    def bw(a, b):
        dlt = per_agent[a] - per_agent[b]
        return {"better": int((dlt < -tol).sum()), "worse": int((dlt > tol).sum()), "unchanged": int((np.abs(dlt) <= tol).sum())}

    for k in names:
        met[k]["vs_status_quo"] = {"combined_unmet_reduction_pct": ma.reduction_pct(met[k]["combined_unmet_bdt"], met["status_quo"]["combined_unmet_bdt"]),
                                   "agents": bw(k, "status_quo")}
    best = ma.best_simple(met)
    inc = ma.incremental(met[ma.ML_POLICY], met[best])
    inc["agents_vs_best_simple"] = bw(ma.ML_POLICY, best)

    def groups_for(name):
        out = {}
        alloc_c = np.sum([plans[name][0][d] for d in days], axis=0)
        alloc_e = np.sum([plans[name][1][d] for d in days], axis=0)
        dlt = per_agent[name] - per_agent["status_quo"]
        for g in GROUPS:
            out[g] = {}
            for val in sorted(agents[g].unique()):
                m = (agents[g] == val).to_numpy()
                s0, s1 = per_agent["status_quo"][m].sum(), per_agent[name][m].sum()
                out[g][str(val)] = {"cash_ratio": float(alloc_c[m].sum() / (tc[m].sum() * len(days))),
                                    "efloat_ratio": float(alloc_e[m].sum() / (te[m].sum() * len(days))),
                                    "combined_unmet_change_pct": -ma.reduction_pct(s1, s0),
                                    "harmed_agents": int((dlt[m] > tol).sum()), "agents": int(m.sum())}
        upp = ((agents["location_cluster"] == "urban_periphery") & (agents["agent_volume_segment"] == "high")).to_numpy()
        out["urban_periphery_high_volume"] = {"agents": int(upp.sum()), "harmed_agents": int((dlt[upp] > tol).sum()),
                                              "status_quo_unmet_bdt": float(per_agent["status_quo"][upp].sum()),
                                              "policy_unmet_bdt": float(per_agent[name][upp].sum()),
                                              "change_pct": -ma.reduction_pct(per_agent[name][upp].sum(), per_agent["status_quo"][upp].sum())}
        return out

    focus = {}
    if seed == 2026:
        prev = json.loads((dw.ARTIFACTS_DIR / "prepositioning_seed_2026.json").read_text())
        for a in prev["agents_better_worse"]["worst_harmed"]:
            i = ids.index(a["agent_id"])
            focus[a["agent_id"]] = {k: float(per_agent[k][i] - per_agent["status_quo"][i])
                                    for k in ("history_proportional", "seasonal_requirement_7d", ma.ML_POLICY)}
    ml_c = met[ma.ML_POLICY]["combined_unmet_bdt"]
    p2c = phase2c["per_seed"][str(seed)]["agentflow_combined_unmet_bdt"]
    res = {"seed": seed, "window": [str(hours[mask][0]), str(hours[mask][-1])], "held_out_days": len(days),
           "status_quo_replay_matches_world": fidelity, "ml_matches_phase_2c": bool(abs(ml_c - p2c) < 0.01),
           "metrics": {k: met[k] for k in ma.OPERATIONAL_POLICIES},
           "oracle": {"label": ORACLE_LABEL, **{k: met[k] for k in ma.ORACLE_POLICIES}},
           "conservation": cons, "conserved_all_policies": all(c["exact"] for c in cons.values()),
           "floor_edge_cases": edges, "best_simple_baseline": best, "incremental": inc,
           "groups": {"best_simple": groups_for(best), ma.ML_POLICY: groups_for(ma.ML_POLICY)},
           "network_daily_budget_bdt": {"cash": int(tc.sum()), "efloat": int(te.sum())}}
    if focus:
        res["phase_2c_worst_harmed_agents_change_vs_status_quo_bdt"] = focus
    if reproduced is not None:
        res["phase_2a_artifacts_reproduced"] = reproduced
    return res


def main() -> None:
    phase2c = json.loads((dw.ARTIFACTS_DIR / "prepositioning_multiseed.json").read_text())
    per_seed = {}
    for seed in ma.SEEDS:
        r = run_seed(seed, phase2c)
        per_seed[seed] = r
        m, i = r["metrics"], r["incremental"]
        print(f"[seed {seed}] combined unmet: SQ={m['status_quo']['combined_unmet_bdt']:,.0f} "
              f"hist={m['history_proportional']['combined_unmet_bdt']:,.0f} seas={m['seasonal_requirement_7d']['combined_unmet_bdt']:,.0f} "
              f"ML={m[ma.ML_POLICY]['combined_unmet_bdt']:,.0f} | best={r['best_simple_baseline']} "
              f"ML incremental={i['combined_unmet_reduction_pct']:.2f}% (cash {i['cash_unmet_reduction_pct']:.2f}%, "
              f"e-float {i['efloat_unmet_reduction_pct']:.2f}%) conserved={r['conserved_all_policies']} "
              f"ml_matches_2c={r['ml_matches_phase_2c']} sq_fidelity={r['status_quo_replay_matches_world']}")
    common = {"label": "Synthetic held-out simulation - Dual-Liquidity World v2 - prepositioning ML attribution (research only)",
              "world_version": dw.WORLD_VERSION, "assumptions_version": dw.ASSUMPTIONS_VERSION,
              "protocol": "docs/ML_ATTRIBUTION_PROTOCOL.md",
              "constants": {"seeds": list(ma.SEEDS), "operational_policies": list(ma.OPERATIONAL_POLICIES),
                            "simple_baselines": list(ma.SIMPLE_BASELINES), "ml_policy": ma.ML_POLICY,
                            "oracle_policies": list(ma.ORACLE_POLICIES), "history_days": ma.HISTORY_DAYS,
                            "modes": ma.MODES, "bar": ma.BAR, "floors_bdt": [pp.FLOOR_CASH_BDT, pp.FLOOR_EFLOAT_BDT]}}
    rows = {}
    for s, r in per_seed.items():
        m = r["metrics"]
        rows[str(s)] = {"best_simple_baseline": r["best_simple_baseline"],
                        **{f"{k}_combined_unmet_bdt": m[k]["combined_unmet_bdt"] for k in ma.OPERATIONAL_POLICIES},
                        **{f"{k}_reduction_vs_status_quo_pct": m[k]["vs_status_quo"]["combined_unmet_reduction_pct"]
                           for k in ma.SIMPLE_BASELINES + (ma.ML_POLICY,)},
                        "oracle_full_day_reduction_vs_status_quo_pct": r["oracle"]["oracle_full_day"]["vs_status_quo"]["combined_unmet_reduction_pct"],
                        "incremental": r["incremental"], "conserved_all_policies": r["conserved_all_policies"],
                        "ml_matches_phase_2c": r["ml_matches_phase_2c"]}
    inc_keys = ("combined_unmet_reduction_pct", "cash_unmet_reduction_pct", "efloat_unmet_reduction_pct", "shortage_event_difference")
    summary = {k: {"mean": float(np.mean([per_seed[s]["incremental"][k] for s in ma.SEEDS])),
                   "median": float(np.median([per_seed[s]["incremental"][k] for s in ma.SEEDS])),
                   "min": float(min(per_seed[s]["incremental"][k] for s in ma.SEEDS)),
                   "max": float(max(per_seed[s]["incremental"][k] for s in ma.SEEDS))} for k in inc_keys}
    multi = {**common, "per_seed": rows, "ml_incremental_summary": summary, "ml_value_bar": ma.ml_value_bar(per_seed)}
    forecast.write_json(dw.ARTIFACTS_DIR / "ml_attribution_seed_2026.json", ev._r({**common, **per_seed[2026]}))
    forecast.write_json(dw.ARTIFACTS_DIR / "ml_attribution_multiseed.json", ev._r(multi))
    print("ML-value bar:", multi["ml_value_bar"])


if __name__ == "__main__":
    main()
