"""Dual-Liquidity Synthetic World v2: a separately versioned, resource-conserving world.

SYNTHETIC DATA FOR RESEARCH - NOT PRODUCTION UPAY DATA. NOT USED BY THE PRODUCTION API.

Why a new world
---------------
The legacy world (``data_gen.py``) tops e-float up to 0.9 x daily cash-out every morning and never
declines a cash-in, so e-float pressure is essentially absent there. That world stays unchanged and
keeps producing the validated cash-side V1/V2 results. This module builds a *separate* world in which
both resources are finite and binding. Its files live in ``ml/data_dual``, ``ml/models_dual`` and
``ml/artifacts_dual``; nothing here reads or writes the legacy paths.

Two coupled resources (agent accounting, per served flow)
---------------------------------------------------------
cash-out: customer receives cash  -> agent cash  -= served_out, e-float += served_out
cash-in : customer deposits cash  -> agent cash  += served_in,  e-float -= served_in
So every served transaction moves value between the agent's two resources and never creates or
destroys working capital. Only the explicit 08:00 status-quo replenishment changes the total.

Within-hour service rule (closed form, maximises served BDT)
------------------------------------------------------------
The data is hourly, not transaction-sequenced. Assumption: *within-hour opposite flows are treated
as available for net settlement; transaction-level ordering is not modelled.* With opening cash C,
opening e-float E, requested cash-out O and cash-in I:

* if O - I > C  (cash-out dominant): served_in = I,         served_out = C + I
* if I - O > E  (cash-in dominant):  served_out = O,        served_in  = E + O
* otherwise:                          served_out = O,        served_in  = I

The two dominant cases are mutually exclusive (C, E >= 0). Each is an upper bound on any feasible
plan (served_out <= C + served_in <= C + I, served_in <= I), so served BDT is maximal; tested.

Pre-registered world rules (fixed before any prevalence, validation or test result was computed)
-------------------------------------------------------------------------------------------------
See ``ASSUMPTIONS`` below and docs/DUAL_WORLD_V2.md. They must not be changed after looking at
held-out results.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import config
from .data_gen import (AGENT_TYPES, ANOMALY_TYPES, DOW_FACTOR, IN_TICKET, OPENING_HOUR, OUT_TICKET,
                       _inject_anomalies, generate_agents, hour_profiles, is_salary_period, salary_factor)

WORLD_VERSION = "dual-liquidity-world-v2"
ASSUMPTIONS_VERSION = "2A.1"

DATA_DIR = config.ML_DIR / "data_dual"
MODELS_DIR = config.ML_DIR / "models_dual"
ARTIFACTS_DIR = config.ML_DIR / "artifacts_dual"
DATASET_PATH = DATA_DIR / "agent_hourly_dual.parquet"
AGENTS_PATH = DATA_DIR / "agents_dual.parquet"
MODEL_PATH = MODELS_DIR / "forecast_models_dual.joblib"

# Same calendar and chronology as the legacy world.
START, N_DAYS, N_AGENTS, SEED = config.START, config.N_DAYS, config.N_AGENTS, config.SEED
TEST_START = config.TEST_START
VALIDATION_START = pd.Timestamp("2026-08-04 00:00")  # chronological slice inside the training period

# Independent random streams (world v2 never consumes the legacy stream).
STREAM_AGENTS, STREAM_ORIENTATION, STREAM_PROVISIONING, STREAM_FLOWS = 21, 22, 23, 24

ASSUMPTIONS = {
    "flow_orientation": {
        # Domestic-remittance corridor: urban workers and businesses deposit cash to send home
        # (net cash-in); rural households withdraw received remittances (net cash-out).
        "cash_in_ratio_median": {"urban_core": 1.25, "urban_periphery": 1.00, "rural": 0.70},
        "cash_in_ratio_lognormal_sigma": 0.15,
        "market_stall_cash_in_multiplier": 1.12,
    },
    "salary_and_remittance": {
        # Urban clusters: wage-remittance sending -> full-strength salary effect on CASH-IN,
        # weak (0.35x) effect on cash-out. Rural: remittance receipt -> full-strength effect on
        # CASH-OUT lagged by 2 days, weak effect on cash-in. Strengths reuse legacy salary_factor.
        "urban_cash_in": "salary_factor(day, cluster, 'out')",
        "urban_cash_out": "salary_factor(day, cluster, 'in')",
        "rural_cash_out": "salary_factor(day - 2 days, 'rural', 'out')",
        "rural_cash_in": "salary_factor(day, 'rural', 'in')",
    },
    "market_day": {
        # Legacy haat-day cash-out uplift kept; traders deposit takings in the afternoon.
        "cash_out_multiplier_all_day": 1.45,
        "cash_in_multiplier": 1.6, "cash_in_hours": [14, 19],
    },
    "legitimate_spikes": {
        # Local events, ~1 per agent per 10 days (legacy rate); direction 50/50.
        "events_per_agent_day": 0.1, "cash_in_share": 0.5, "multiplier": [1.6, 2.6],
        "duration_h": [2, 5], "hours": [9, 19],
    },
    "provisioning": {
        # Status-quo manual reset at 08:00 for BOTH resources, symmetric rule, same range as the
        # legacy cash provisioning, independent draws per resource.
        "reset_hour": OPENING_HOUR,
        "cash_target": "expected_daily_cash_out x U(0.42, 0.85)",
        "efloat_target": "expected_daily_cash_in x U(0.42, 0.85)",
        "fraction_range": [0.42, 0.85], "rounding_bdt": 500,
    },
    "service_rule": "within-hour opposite flows net-settle; transaction ordering not modelled",
    "anomalies": "legacy behavioural anomaly injection, labelled separately from legitimate flow events",
}


@dataclass
class DualWorld:
    agents: pd.DataFrame
    hourly: pd.DataFrame


# ---------------------------------------------------------------- service rule
def serve_hour(cash, efloat, req_out, req_in):
    """Closed-form, resource-conserving service for one hour (vectorised over agents).

    Returns (served_out, served_in, cash_after, efloat_after).
    """
    cash = np.asarray(cash, float)
    efloat = np.asarray(efloat, float)
    req_out = np.asarray(req_out, float)
    req_in = np.asarray(req_in, float)
    d = req_out - req_in
    served_out = np.where(d > cash, cash + req_in, req_out)
    served_in = np.where(-d > efloat, efloat + req_out, req_in)
    cash_after = cash + served_in - served_out
    efloat_after = efloat + served_out - served_in
    return served_out, served_in, cash_after, efloat_after


def simulate_dual(req_out, req_in, target_cash, target_efloat, hours_of_day,
                  initial_cash=None, initial_efloat=None) -> dict:
    """Hour-by-hour dual-resource simulation under the status-quo 08:00 reset.

    req_out, req_in: (n_hours, n_agents) requested flows. Returns dict of (n_hours, n_agents) arrays:
    cash, efloat (end of hour), served_out, served_in, unmet_out, unmet_in,
    cash_replenishment, efloat_replenishment (external top-up(+)/sweep(-) at the reset hour).
    """
    n_hours, n_agents = req_out.shape
    tc = np.asarray(target_cash, float)
    te = np.asarray(target_efloat, float)
    cash = tc.copy() if initial_cash is None else np.asarray(initial_cash, float).copy()
    ef = te.copy() if initial_efloat is None else np.asarray(initial_efloat, float).copy()
    out = {k: np.zeros((n_hours, n_agents)) for k in
           ("cash", "efloat", "served_out", "served_in", "unmet_out", "unmet_in",
            "cash_replenishment", "efloat_replenishment")}
    for t in range(n_hours):
        if hours_of_day[t] == OPENING_HOUR:
            out["cash_replenishment"][t] = tc - cash
            out["efloat_replenishment"][t] = te - ef
            cash, ef = tc.copy(), te.copy()
        so, si, cash, ef = serve_hour(cash, ef, req_out[t], req_in[t])
        out["served_out"][t], out["served_in"][t] = so, si
        out["unmet_out"][t], out["unmet_in"][t] = req_out[t] - so, req_in[t] - si
        out["cash"][t], out["efloat"][t] = cash, ef
    return out


# ---------------------------------------------------------------- generator
def _agents(seed: int, n_agents: int) -> pd.DataFrame:
    agents = generate_agents(np.random.default_rng([seed, STREAM_AGENTS]), n_agents)
    fo = ASSUMPTIONS["flow_orientation"]
    r_or = np.random.default_rng([seed, STREAM_ORIENTATION])
    med = agents["location_cluster"].map(fo["cash_in_ratio_median"]).to_numpy()
    ratio = med * r_or.lognormal(0.0, fo["cash_in_ratio_lognormal_sigma"], len(agents))
    ratio = np.where(agents["agent_type"] == "market_stall", ratio * fo["market_stall_cash_in_multiplier"], ratio)
    agents["cash_in_ratio"] = ratio.round(4)
    pv = ASSUMPTIONS["provisioning"]
    r_pv = np.random.default_rng([seed, STREAM_PROVISIONING])
    lo, hi = pv["fraction_range"]
    cash_frac = r_pv.uniform(lo, hi, len(agents))
    ef_frac = r_pv.uniform(lo, hi, len(agents))
    out_d = agents["base_daily_cash_out"].to_numpy()
    in_d = out_d * agents["cash_in_ratio"].to_numpy()
    agents["expected_daily_cash_in"] = in_d.round(2)
    agents["cash_provisioning_fraction"] = cash_frac.round(4)
    agents["efloat_provisioning_fraction"] = ef_frac.round(4)
    agents["target_cash_level"] = np.round(out_d * cash_frac / 500.0) * 500.0
    agents["target_efloat_level"] = np.round(in_d * ef_frac / 500.0) * 500.0
    return agents


def generate_world(seed: int = SEED, n_agents: int = N_AGENTS, n_days: int = N_DAYS,
                   start: pd.Timestamp = START) -> DualWorld:
    agents = _agents(seed, n_agents)
    rng = np.random.default_rng([seed, STREAM_FLOWS])
    n_hours = n_days * 24
    ts = pd.date_range(start, periods=n_hours, freq="h")
    hod, dow, dom = ts.hour.to_numpy(), ts.dayofweek.to_numpy(), ts.day.to_numpy()
    dom_lag2 = (ts - pd.Timedelta(days=2)).day.to_numpy()
    day_idx = np.arange(n_hours) // 24
    profiles = hour_profiles()
    md = ASSUMPTIONS["market_day"]
    in_h0, in_h1 = md["cash_in_hours"]

    out_exp = np.empty((n_hours, n_agents))
    in_exp = np.empty((n_hours, n_agents))
    for j, a in agents.iterrows():
        c = a["location_cluster"]
        dowf = DOW_FACTOR[c][dow].copy()
        dowf_in = dowf.copy()
        if a["market_day"] >= 0:
            haat = dow == a["market_day"]
            dowf = np.where(haat, dowf * md["cash_out_multiplier_all_day"], dowf)
            dowf_in = np.where(haat & (hod >= in_h0) & (hod <= in_h1), dowf_in * md["cash_in_multiplier"], dowf_in)
        if c == "rural":
            sal_out, sal_in = salary_factor(dom_lag2, c, "out"), salary_factor(dom, c, "in")
        else:
            sal_out, sal_in = salary_factor(dom, c, "in"), salary_factor(dom, c, "out")
        daily_out = a["base_daily_cash_out"]
        daily_in = daily_out * a["cash_in_ratio"]
        out_exp[:, j] = daily_out * profiles[c]["out"][hod] * dowf * sal_out
        in_exp[:, j] = daily_in * profiles[c]["in"][hod] * dowf_in * sal_in

    day_shock = np.zeros((n_days, n_agents))
    eps = rng.normal(0, 0.10, size=(n_days, n_agents))
    for d in range(1, n_days):
        day_shock[d] = 0.6 * day_shock[d - 1] + eps[d]
    regime = np.exp(day_shock[day_idx])

    sp = ASSUMPTIONS["legitimate_spikes"]
    spike_out = np.ones((n_hours, n_agents))
    spike_in = np.ones((n_hours, n_agents))
    flow_event = np.full((n_hours, n_agents), "", dtype=object)
    for _ in range(int(n_agents * n_days * sp["events_per_agent_day"])):
        a = int(rng.integers(0, n_agents))
        t0 = int(rng.integers(0, n_hours - 6))
        is_in = rng.random() < sp["cash_in_share"]
        dur = int(rng.integers(sp["duration_h"][0], sp["duration_h"][1] + 1))
        mult = rng.uniform(*sp["multiplier"])
        if sp["hours"][0] <= hod[t0] <= sp["hours"][1]:
            target = spike_in if is_in else spike_out
            target[t0:t0 + dur, a] *= mult
            flow_event[t0:t0 + dur, a] = "cash_in_surge" if is_in else "cash_out_surge"
    for j, a in agents.iterrows():
        if a["market_day"] >= 0:
            m = (dow == a["market_day"]) & (hod >= in_h0) & (hod <= in_h1)
            flow_event[m & (flow_event[:, j] == ""), j] = "haat_trader_deposits"

    noise_out = rng.lognormal(-0.5 * 0.33 ** 2, 0.33, size=(n_hours, n_agents))
    noise_in = rng.lognormal(-0.5 * 0.33 ** 2, 0.33, size=(n_hours, n_agents))
    label, a_type, out_m, in_m, cnt_m, night_add = _inject_anomalies(rng, n_agents, n_hours, ts, n_hours - 30)

    base_daily = agents["base_daily_cash_out"].to_numpy()[None, :]
    req_out = np.round(out_exp * regime * spike_out * noise_out * out_m + night_add * base_daily, -1)
    req_in = np.round(in_exp * regime * spike_in * noise_in * in_m + 0.5 * night_add * base_daily, -1)

    clusters = agents["location_cluster"].to_numpy()
    out_ticket = np.array([OUT_TICKET[c] for c in clusters])[None, :]
    in_ticket = np.array([IN_TICKET[c] for c in clusters])[None, :]
    out_cnt = rng.poisson(req_out / out_ticket * cnt_m)
    in_cnt = rng.poisson(req_in / in_ticket * np.where(a_type == "cash_churn", cnt_m, 1.0))
    activity = (req_out + req_in) / (out_ticket + in_ticket)
    send_cnt = rng.poisson(0.9 * activity)
    pay_cnt = rng.poisson(0.6 * activity)

    sim = simulate_dual(req_out, req_in, agents["target_cash_level"].to_numpy(),
                        agents["target_efloat_level"].to_numpy(), hod)
    txn_cnt = out_cnt + in_cnt + send_cnt + pay_cnt
    cash_txn = np.maximum(out_cnt + in_cnt, 1)
    unmet_out, unmet_in = sim["unmet_out"], sim["unmet_in"]
    hourly = pd.DataFrame({
        "agent_id": np.tile(agents["agent_id"].to_numpy(), n_hours),
        "timestamp": np.repeat(ts.to_numpy(), n_agents),
        "cash_balance": sim["cash"].ravel(),
        "efloat_balance": sim["efloat"].ravel(),
        "requested_cash_out": req_out.ravel(),
        "served_cash_out": sim["served_out"].ravel(),
        "unmet_cash_out": unmet_out.ravel(),
        "requested_cash_in": req_in.ravel(),
        "served_cash_in": sim["served_in"].ravel(),
        "unmet_cash_in": unmet_in.ravel(),
        "cash_replenishment": sim["cash_replenishment"].ravel(),
        "efloat_replenishment": sim["efloat_replenishment"].ravel(),
        # aliases expected by the shared feature pipeline: REQUESTED flows
        "cash_out_amount": req_out.ravel(),
        "cash_in_amount": req_in.ravel(),
        "cash_out_count": out_cnt.ravel().astype(np.int32),
        "cash_in_count": in_cnt.ravel().astype(np.int32),
        "send_money_count": send_cnt.ravel().astype(np.int32),
        "payment_count": pay_cnt.ravel().astype(np.int32),
        "transaction_count": txn_cnt.ravel().astype(np.int32),
        "average_transaction_value": ((req_out + req_in) / cash_txn).ravel().round(2),
        "hour": np.repeat(hod, n_agents).astype(np.int8),
        "day_of_week": np.repeat(dow, n_agents).astype(np.int8),
        "is_weekend": np.repeat(np.isin(dow, [4, 5]), n_agents),
        "is_salary_period": np.repeat(is_salary_period(dom), n_agents),
        "cash_shortage_event": (unmet_out.ravel() > 0).astype(np.int8),
        "efloat_shortage_event": (unmet_in.ravel() > 0).astype(np.int8),
        "dual_shortage_event": ((unmet_out.ravel() > 0) & (unmet_in.ravel() > 0)).astype(np.int8),
        "liquidity_shortage": (unmet_out.ravel() > 0).astype(np.int8),  # legacy name (cash side)
        "flow_event": flow_event.ravel().astype(str),
        "known_anomaly_label": label.ravel(),
        "anomaly_type": a_type.ravel().astype(str),
    })
    hourly = hourly.sort_values(["agent_id", "timestamp"], kind="stable").reset_index(drop=True)
    return DualWorld(agents=agents, hourly=hourly)


def save(world: DualWorld) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    world.agents.to_parquet(AGENTS_PATH, index=False)
    world.hourly.to_parquet(DATASET_PATH, index=False)


def load() -> DualWorld:
    return DualWorld(agents=pd.read_parquet(AGENTS_PATH), hourly=pd.read_parquet(DATASET_PATH))


# ---------------------------------------------------------------- symmetric pressure matrix
RESOURCE_STATUS = ("COVERED", "WATCH", "PRESSURE")
LIQUIDITY_STATES = ("HEALTHY", "WATCH", "CASH_PRESSURE", "EFLOAT_PRESSURE", "DUAL_PRESSURE")


def resource_status(balance, req_p50, req_p90) -> np.ndarray:
    """PRESSURE if balance < P50 requirement, WATCH if only the P90 requirement is not covered."""
    bal = np.asarray(balance, float)
    p50 = np.maximum(np.asarray(req_p50, float), 0.0)
    p90 = np.maximum(np.asarray(req_p90, float), p50)
    return np.select([bal < p50, bal < p90], ["PRESSURE", "WATCH"], default="COVERED").astype(object)


def liquidity_state_matrix(cash_status, efloat_status) -> np.ndarray:
    """Symmetric deterministic state from the two resource statuses (neither resource favoured)."""
    c = np.asarray(cash_status, dtype=object)
    e = np.asarray(efloat_status, dtype=object)
    cp, ep = c == "PRESSURE", e == "PRESSURE"
    watch = (c == "WATCH") | (e == "WATCH")
    return np.select([cp & ep, cp, ep, watch],
                     ["DUAL_PRESSURE", "CASH_PRESSURE", "EFLOAT_PRESSURE", "WATCH"],
                     default="HEALTHY").astype(object)


__all__ = ["WORLD_VERSION", "ASSUMPTIONS_VERSION", "ASSUMPTIONS", "serve_hour", "simulate_dual",
           "generate_world", "resource_status", "liquidity_state_matrix", "ANOMALY_TYPES", "AGENT_TYPES"]
