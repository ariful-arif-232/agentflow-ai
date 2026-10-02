"""Phase 2C: forecast-guided dual-liquidity prepositioning, held-out simulation (research only).

Pre-registered protocol: docs/PREPOSITIONING_PROTOCOL.md. For each pre-registered seed the unchanged
Dual World v2 (assumptions 2A.1) and its unchanged Phase 2A models are rebuilt; earlier dual-world and
complementarity artifacts are never overwritten. Writes ml/artifacts_dual/prepositioning_seed_2026.json
and ml/artifacts_dual/prepositioning_multiseed.json.

Usage:  python ml/scripts/run_prepositioning.py
"""
from __future__ import annotations

import _bootstrap  # noqa: F401

import numpy as np
import pandas as pd

from agentflow import dual_world as dw, dual_world_eval as ev, forecast, prepositioning as pp
from agentflow.features import EFLOAT_TARGET

ORACLE_LABEL = "ORACLE - evaluation only, impossible operationally"
PHASE_2A_FILES = ("world_summary.json", "forecast_metrics.json", "status_quo_impact.json")


def matrices(world: dw.DualWorld, start: pd.Timestamp):
    h = world.hourly[world.hourly["timestamp"] >= start - pd.Timedelta(hours=1)]
    piv = lambda col: h.pivot(index="timestamp", columns="agent_id", values=col).sort_index(axis=1)  # noqa: E731
    ro, ri = piv("requested_cash_out"), piv("requested_cash_in")
    cb, eb = piv("cash_balance"), piv("efloat_balance")
    uo, ui = piv("unmet_cash_out"), piv("unmet_cash_in")
    hours = ro.index[1:]
    return (hours, list(ro.columns), ro.iloc[1:].to_numpy(), ri.iloc[1:].to_numpy(),
            cb.iloc[0].to_numpy(), eb.iloc[0].to_numpy(), uo.iloc[1:].to_numpy(), ui.iloc[1:].to_numpy())


def full_day_requirement(req_out, req_in, hours, day):
    """ORACLE ONLY: actual peak requirement over the replay day 08:00 -> 07:59 (or end of data)."""
    m = (hours >= day + pd.Timedelta(hours=8)) & (hours < day + pd.Timedelta(hours=32))
    net = np.cumsum(req_out[m] - req_in[m], axis=0)
    return np.maximum(net.max(axis=0), 0.0), np.maximum((-net).max(axis=0), 0.0)


def run_seed(seed: int) -> dict:
    world = dw.generate_world(seed=seed)
    arts, state = ev.run(world, model_path=dw.MODELS_DIR / f"forecast_models_dual_seed_{seed}.joblib", return_state=True)
    reproduced = None
    if seed == dw.SEED:
        import json
        reproduced = all(json.loads(json.dumps(arts[n], default=float)) == json.loads((dw.ARTIFACTS_DIR / n).read_text())
                         for n in PHASE_2A_FILES)
    f, bundle = state["features"], state["bundle"]
    agents = world.agents.sort_values("agent_id").reset_index(drop=True)
    days = pd.date_range(dw.TEST_START, f["timestamp"].max().normalize(), freq="D")
    hours, ids, req_out, req_in, c0, e0, rec_uo, rec_ui = matrices(world, dw.TEST_START)
    assert ids == list(agents["agent_id"])
    sq_c, sq_e = agents["target_cash_level"].round().astype(np.int64).to_numpy(), agents["target_efloat_level"].round().astype(np.int64).to_numpy()

    plans = {"status_quo": ({}, {}), "agentflow": ({}, {}), "oracle_6h": ({}, {}), "oracle_full_day": ({}, {})}
    alloc_rows, edges = [], {"agentflow": 0, "oracle_6h": 0, "oracle_full_day": 0}
    for d in days:
        rows = f[f["timestamp"] == d + pd.Timedelta(hours=pp.FORECAST_ROW_HOUR)].sort_values("agent_id")
        view = rows[["agent_id", "district", "target_cash_level", "target_efloat_level"]].copy()
        view = view.join(bundle.predict(rows)[["pred_net_requirement_p90_6h", "pred_efloat_requirement_p90_6h"]])
        a, e = pp.allocate_day(view)
        edges["agentflow"] += e
        plans["agentflow"][0][d], plans["agentflow"][1][d] = a["alloc_cash"].to_numpy(), a["alloc_efloat"].to_numpy()
        plans["status_quo"][0][d], plans["status_quo"][1][d] = sq_c, sq_e
        alloc_rows.append(a.assign(day=d))
        # ---- oracles (evaluation only; never feed the policy)
        o6 = view.copy()
        o6["pred_net_requirement_p90_6h"] = rows["future_6h_net_cash_demand"].to_numpy()
        o6["pred_efloat_requirement_p90_6h"] = rows[EFLOAT_TARGET].to_numpy()
        a6, e6 = pp.allocate_day(o6)
        edges["oracle_6h"] += e6
        plans["oracle_6h"][0][d], plans["oracle_6h"][1][d] = a6["alloc_cash"].to_numpy(), a6["alloc_efloat"].to_numpy()
        fc, fe = full_day_requirement(req_out, req_in, hours, d)
        of = view.copy()
        of["pred_net_requirement_p90_6h"], of["pred_efloat_requirement_p90_6h"] = fc, fe
        af_, ef_ = pp.allocate_day(of)
        edges["oracle_full_day"] += ef_
        plans["oracle_full_day"][0][d], plans["oracle_full_day"][1][d] = af_["alloc_cash"].to_numpy(), af_["alloc_efloat"].to_numpy()

    alloc = pd.concat(alloc_rows, ignore_index=True).merge(agents[["agent_id", "location_cluster", "agent_volume_segment"]], on="agent_id")
    # ---- exact conservation proof (every day, every district, every plan)
    cons = {"exact": True, "max_abs_district_diff_bdt": 0, "days": len(days)}
    for name, (pc, pe) in plans.items():
        for d in days:
            for res, p, sq in (("cash", pc[d], sq_c), ("efloat", pe[d], sq_e)):
                assert (p >= 0).all()
                diff = pd.Series(p - sq).groupby(agents["district"].to_numpy()).sum().abs().max()
                cons["max_abs_district_diff_bdt"] = max(cons["max_abs_district_diff_bdt"], int(diff))
                if diff != 0 or int(p.sum()) != int(sq.sum()):
                    cons["exact"] = False
    cons["network_daily_cash_bdt"] = int(sq_c.sum())
    cons["network_daily_efloat_bdt"] = int(sq_e.sum())
    cons["district_daily_budgets"] = {dist: {"cash": int(g["target_cash_level"].sum()), "efloat": int(g["target_efloat_level"].sum())}
                                      for dist, g in agents.groupby("district")}

    mask = np.asarray(hours >= dw.TEST_START + pd.Timedelta(hours=pp.DECISION_HOUR))
    sims = {k: pp.replay(req_out, req_in, hours, c0, e0, pc, pe) for k, (pc, pe) in plans.items()}
    fidelity = bool(np.allclose(sims["status_quo"]["unmet_out"], rec_uo) and np.allclose(sims["status_quo"]["unmet_in"], rec_ui))
    met = {k: pp.service_metrics(s, req_out, req_in, mask) for k, s in sims.items()}
    sq, af = met["status_quo"], met["agentflow"]
    wc = float(sq_c.sum() + sq_e.sum())
    avoided = sq["combined_unmet_bdt"] - af["combined_unmet_bdt"]
    impact = {"cash_unmet_reduction_pct": -pp.pct_change(af["unmet_cash_out_bdt"], sq["unmet_cash_out_bdt"]),
              "efloat_unmet_reduction_pct": -pp.pct_change(af["unmet_cash_in_bdt"], sq["unmet_cash_in_bdt"]),
              "combined_unmet_reduction_pct": -pp.pct_change(af["combined_unmet_bdt"], sq["combined_unmet_bdt"]),
              "shortage_event_reduction_pct": -pp.pct_change(af["shortage_events_total"], sq["shortage_events_total"]),
              "shortage_events_avoided": sq["shortage_events_total"] - af["shortage_events_total"],
              "combined_fill_rate_change_pp": 100 * (af["combined_fill_rate"] - sq["combined_fill_rate"]),
              "unmet_bdt_avoided": avoided,
              "unmet_avoided_per_1m_daily_working_capital_bdt": avoided / (wc / 1e6),
              "extra_liquidity_bdt": 0}
    per_agent = lambda s: (s["unmet_out"][mask] + s["unmet_in"][mask]).sum(axis=0)  # noqa: E731
    delta = per_agent(sims["agentflow"]) - per_agent(sims["status_quo"])
    tol = pp.BETTER_WORSE_TOLERANCE_BDT
    worst = np.argsort(-delta)[:5]
    agents_bw = {"better": int((delta < -tol).sum()), "worse": int((delta > tol).sum()),
                 "unchanged": int((np.abs(delta) <= tol).sum()),
                 "worst_harmed": [{"agent_id": ids[i], "location_cluster": agents.loc[i, "location_cluster"],
                                   "segment": agents.loc[i, "agent_volume_segment"], "combined_unmet_change_bdt": float(delta[i])}
                                  for i in worst if delta[i] > tol],
                 "total_harm_bdt": float(delta[delta > tol].sum()), "total_benefit_bdt": float(-delta[delta < -tol].sum())}
    dc, de = alloc["alloc_cash"] - alloc["sq_cash"], alloc["alloc_efloat"] - alloc["sq_efloat"]
    shifts = {"max_increase_cash_bdt": int(dc.max()), "max_decrease_cash_bdt": int(dc.min()),
              "max_increase_efloat_bdt": int(de.max()), "max_decrease_efloat_bdt": int(de.min()),
              "floor_only_agent_days_cash": int((alloc["alloc_cash"] == pp.FLOOR_CASH_BDT).sum()),
              "floor_only_agent_days_efloat": int((alloc["alloc_efloat"] == pp.FLOOR_EFLOAT_BDT).sum()),
              "agent_days": int(len(alloc)), "floor_edge_cases": edges}
    ratios, flags = {}, []
    lo, hi = pp.CONCENTRATION_FLAG
    for gcol in ("location_cluster", "agent_volume_segment", "district"):
        ratios[gcol] = {}
        for g, sub in alloc.groupby(gcol):
            rc, re_ = sub["alloc_cash"].sum() / sub["sq_cash"].sum(), sub["alloc_efloat"].sum() / sub["sq_efloat"].sum()
            ratios[gcol][str(g)] = {"cash_ratio": float(rc), "efloat_ratio": float(re_)}
            for res, r in (("cash", rc), ("efloat", re_)):
                if r < lo or r > hi:
                    flags.append(f"{gcol}={g} {res} ratio {r:.2f}")
    group_impact = {}
    for gcol in ("location_cluster", "agent_volume_segment"):
        group_impact[gcol] = {}
        for g in sorted(agents[gcol].unique()):
            m = (agents[gcol] == g).to_numpy()
            s0, s1 = per_agent(sims["status_quo"])[m].sum(), per_agent(sims["agentflow"])[m].sum()
            group_impact[gcol][str(g)] = {"status_quo_unmet_bdt": float(s0), "agentflow_unmet_bdt": float(s1),
                                          "change_pct": pp.pct_change(s1, s0)}
    oracle = {"label": ORACLE_LABEL}
    for k in ("oracle_6h", "oracle_full_day"):
        oracle[k] = {**met[k], "combined_unmet_reduction_pct": -pp.pct_change(met[k]["combined_unmet_bdt"], sq["combined_unmet_bdt"]),
                     "cash_unmet_reduction_pct": -pp.pct_change(met[k]["unmet_cash_out_bdt"], sq["unmet_cash_out_bdt"]),
                     "efloat_unmet_reduction_pct": -pp.pct_change(met[k]["unmet_cash_in_bdt"], sq["unmet_cash_in_bdt"])}
    res = {"seed": seed, "world_hash": arts["world_summary.json"]["world_hash"],
           "window": [str(hours[mask][0]), str(hours[mask][-1])], "held_out_days": len(days),
           "status_quo": sq, "agentflow": af, "impact": impact, "conservation": cons,
           "status_quo_replay_matches_world": fidelity, "agents_better_worse": agents_bw,
           "allocation_shifts": shifts, "allocation_ratios": ratios, "concentration_flags": flags,
           "group_impact": group_impact, "oracle": oracle}
    if reproduced is not None:
        res["phase_2a_artifacts_reproduced"] = reproduced
    res["bar"] = pp.seed_bar(sq, af, cons["exact"])
    return res


def main() -> None:
    per_seed = {}
    for seed in pp.SEEDS:
        r = run_seed(seed)
        per_seed[seed] = r
        i = r["impact"]
        print(f"[seed {seed}] combined -{i['combined_unmet_reduction_pct']:.2f}% cash -{i['cash_unmet_reduction_pct']:.2f}% "
              f"efloat -{i['efloat_unmet_reduction_pct']:.2f}% better={r['agents_better_worse']['better']} worse={r['agents_better_worse']['worse']} "
              f"conserved={r['conservation']['exact']} sq_fidelity={r['status_quo_replay_matches_world']} bar={r['bar']['passes']}")
    common = {"label": "Synthetic held-out simulation - Dual-Liquidity World v2 - forecast-guided prepositioning (research only)",
              "world_version": dw.WORLD_VERSION, "assumptions_version": dw.ASSUMPTIONS_VERSION,
              "protocol": "docs/PREPOSITIONING_PROTOCOL.md",
              "constants": {"seeds": list(pp.SEEDS), "floor_cash_bdt": pp.FLOOR_CASH_BDT, "floor_efloat_bdt": pp.FLOOR_EFLOAT_BDT,
                            "decision_hour": pp.DECISION_HOUR, "forecast_row_hour": pp.FORECAST_ROW_HOUR,
                            "forecast_signal": "6h P90 cash and e-float requirement", "bar": pp.BAR,
                            "concentration_flag": list(pp.CONCENTRATION_FLAG)}}
    keys = ["cash_unmet_reduction_pct", "efloat_unmet_reduction_pct", "combined_unmet_reduction_pct",
            "shortage_event_reduction_pct", "combined_fill_rate_change_pp", "unmet_avoided_per_1m_daily_working_capital_bdt"]
    rows = {}
    for s, r in per_seed.items():
        rows[str(s)] = {**{k: r["impact"][k] for k in keys},
                        "agents_better": r["agents_better_worse"]["better"], "agents_worse": r["agents_better_worse"]["worse"],
                        "resources_exactly_conserved": r["conservation"]["exact"],
                        "status_quo_combined_unmet_bdt": r["status_quo"]["combined_unmet_bdt"],
                        "agentflow_combined_unmet_bdt": r["agentflow"]["combined_unmet_bdt"],
                        "oracle_6h_combined_reduction_pct": r["oracle"]["oracle_6h"]["combined_unmet_reduction_pct"],
                        "oracle_full_day_combined_reduction_pct": r["oracle"]["oracle_full_day"]["combined_unmet_reduction_pct"],
                        "concentration_flags": len(r["concentration_flags"]), "bar": r["bar"]}
    num = [k for k, v in rows["2026"].items() if isinstance(v, (int, float)) and not isinstance(v, bool)]
    summary = {k: {"mean": float(np.mean([rows[s][k] for s in rows])), "median": float(np.median([rows[s][k] for s in rows])),
                   "min": float(min(rows[s][k] for s in rows)), "max": float(max(rows[s][k] for s in rows))} for k in num}
    multi = {**common, "per_seed": rows, "robustness_summary": summary, "overall_bar": pp.overall_bar(per_seed)}
    forecast.write_json(dw.ARTIFACTS_DIR / "prepositioning_seed_2026.json", ev._r({**common, **per_seed[2026]}))
    forecast.write_json(dw.ARTIFACTS_DIR / "prepositioning_multiseed.json", ev._r(multi))
    print("overall bar:", multi["overall_bar"])


if __name__ == "__main__":
    main()
