"""Deterministic synthetic MFS agent dataset generator.

SYNTHETIC DATA FOR HACKATHON PROTOTYPING — NOT PRODUCTION UPAY DATA.

The generator produces hourly observations for a network of synthetic agents with
realistic, *learnable* structure:

* hour-of-day demand profiles that differ by location cluster,
* weekday / weekend differences (Bangladesh weekend: Friday + Saturday),
* salary-period effects (end / start of month), strongest in urban-periphery clusters,
* weekly market ("haat") days for rural agents,
* agent-specific baselines, volume segments and cash-in / cash-out mixes,
* persistent day-level demand regimes (AR(1)), temporary legitimate demand spikes,
* multiplicative stochastic noise,
* intentionally injected behavioural anomalies with ground-truth labels.

Cash balances are simulated with a simple *manual* operating policy (the
"status quo"): every morning at 08:00 the agent's cash drawer is reset to a fixed,
static target level. That policy ignores salary periods, market days and spikes,
which is what produces realistic liquidity shortages.

No real person, phone number, name or account is generated — agents are identified
only by synthetic IDs (AG-0001 ...).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import config

# District -> (latitude, longitude, share of agents, urban tendency 0..1)
DISTRICTS: dict[str, tuple[float, float, int, float]] = {
    "Dhaka": (23.8103, 90.4125, 50, 0.85),
    "Gazipur": (24.0023, 90.4264, 25, 0.55),
    "Chattogram": (22.3569, 91.7832, 35, 0.70),
    "Sylhet": (24.8949, 91.8687, 20, 0.40),
    "Rajshahi": (24.3745, 88.6042, 20, 0.35),
    "Khulna": (22.8456, 89.5403, 20, 0.40),
    "Rangpur": (25.7439, 89.2752, 15, 0.25),
    "Barishal": (22.7010, 90.3535, 15, 0.30),
}
CLUSTERS = ("urban_core", "urban_periphery", "rural")
SEGMENTS = ("low", "medium", "high")
AGENT_TYPES = ("retail_shop", "grocery", "pharmacy", "market_stall", "transport_hub")

# Expected daily cash-out demand (BDT) by volume segment.
SEGMENT_DAILY_OUT = {"low": 45_000.0, "medium": 110_000.0, "high": 230_000.0}
# Cash-in / cash-out ratio by cluster (urban businesses deposit more cash).
CLUSTER_IN_RATIO = {"urban_core": 1.10, "urban_periphery": 0.80, "rural": 0.68}
# Distance band (km) from district centroid by cluster.
CLUSTER_RADIUS_KM = {"urban_core": (0.3, 4.0), "urban_periphery": (4.0, 12.0), "rural": (12.0, 32.0)}
# Average ticket size (BDT).
OUT_TICKET = {"urban_core": 2_100.0, "urban_periphery": 1_700.0, "rural": 1_300.0}
IN_TICKET = {"urban_core": 3_000.0, "urban_periphery": 2_200.0, "rural": 1_800.0}

ANOMALY_TYPES = ("rapid_burst", "large_ticket", "odd_hour", "cash_churn")
OPENING_HOUR = 8  # manual daily drawer reset happens at the start of this hour


def _bump(hours: np.ndarray, center: float, width: float) -> np.ndarray:
    return np.exp(-0.5 * ((hours - center) / width) ** 2)


def hour_profiles() -> dict[str, dict[str, np.ndarray]]:
    """Normalised 24h demand profiles (sum to 1) per cluster for cash-out and cash-in."""
    h = np.arange(24, dtype=float)
    profiles: dict[str, dict[str, np.ndarray]] = {}
    specs = {
        # (out peaks), (in peaks), opening-hour window
        "urban_core": ([(11.5, 1.6, 1.0), (18.5, 1.8, 1.25)], [(13.5, 2.0, 1.0), (20.0, 1.5, 1.2)], (8, 22)),
        "urban_periphery": ([(10.0, 1.5, 1.0), (19.0, 1.6, 1.35)], [(14.0, 2.0, 0.9), (20.0, 1.4, 1.0)], (7, 22)),
        "rural": ([(10.0, 1.6, 1.3), (16.0, 1.8, 1.0)], [(12.5, 2.0, 1.0), (17.5, 1.5, 0.9)], (7, 20)),
    }
    for cluster, (out_peaks, in_peaks, (open_h, close_h)) in specs.items():
        open_mask = ((h >= open_h) & (h <= close_h)).astype(float)
        night = 0.015  # residual night-time activity
        out = sum(a * _bump(h, c, w) for c, w, a in out_peaks) * open_mask + night
        inn = sum(a * _bump(h, c, w) for c, w, a in in_peaks) * open_mask + night
        profiles[cluster] = {"out": out / out.sum(), "in": inn / inn.sum()}
    return profiles


# Day-of-week multipliers (Mon=0 .. Sun=6). Bangladesh weekend = Friday (4) + Saturday (5).
DOW_FACTOR = {
    "urban_core": np.array([1.02, 1.00, 1.03, 1.12, 0.72, 0.86, 1.05]),
    "urban_periphery": np.array([1.00, 0.99, 1.02, 1.10, 0.80, 0.92, 1.04]),
    "rural": np.array([1.00, 1.00, 1.00, 1.05, 0.88, 0.95, 1.00]),
}


def salary_factor(day_of_month: np.ndarray, cluster: str, kind: str) -> np.ndarray:
    """Salary-period uplift: strongest on days 27..3, tapering on 25-26 and 4-5."""
    d = day_of_month
    peak = (d >= 27) | (d <= 3)
    shoulder = ((d >= 25) & (d <= 26)) | ((d >= 4) & (d <= 5))
    strength = {"urban_core": 0.30, "urban_periphery": 0.62, "rural": 0.28}[cluster]
    if kind == "in":
        strength *= 0.35
    return 1.0 + strength * peak + 0.45 * strength * shoulder


def is_salary_period(day_of_month: np.ndarray) -> np.ndarray:
    return (day_of_month >= 25) | (day_of_month <= 5)


@dataclass
class GeneratedData:
    agents: pd.DataFrame
    hourly: pd.DataFrame


def generate_agents(rng: np.random.Generator, n_agents: int) -> pd.DataFrame:
    shares = np.array([v[2] for v in DISTRICTS.values()], dtype=float)
    counts = np.floor(shares / shares.sum() * n_agents).astype(int)
    counts[0] += n_agents - counts.sum()
    rows = []
    idx = 1
    for (district, (lat0, lon0, _, urban)), count in zip(DISTRICTS.items(), counts):
        for _ in range(count):
            p_core = 0.55 * urban
            p_peri = 0.25 + 0.15 * urban
            cluster = rng.choice(CLUSTERS, p=[p_core, p_peri, 1 - p_core - p_peri])
            segment = rng.choice(SEGMENTS, p={"urban_core": [0.25, 0.45, 0.30],
                                              "urban_periphery": [0.30, 0.45, 0.25],
                                              "rural": [0.50, 0.38, 0.12]}[cluster])
            agent_type = rng.choice(AGENT_TYPES, p=[0.35, 0.25, 0.12, 0.16, 0.12])
            r_lo, r_hi = CLUSTER_RADIUS_KM[cluster]
            radius = rng.uniform(r_lo, r_hi)
            theta = rng.uniform(0, 2 * np.pi)
            lat = lat0 + (radius * np.sin(theta)) / 111.0
            lon = lon0 + (radius * np.cos(theta)) / (111.0 * np.cos(np.radians(lat0)))
            base_out = SEGMENT_DAILY_OUT[segment] * rng.lognormal(0.0, 0.22)
            in_ratio = CLUSTER_IN_RATIO[cluster] * rng.lognormal(0.0, 0.12)
            if agent_type == "market_stall":
                in_ratio *= 1.12
            # Static manual provisioning: a fraction of expected daily cash-out.
            provisioning = rng.uniform(0.42, 0.85)
            rows.append({
                "agent_id": f"AG-{idx:04d}",
                "district": district,
                "location_cluster": str(cluster),
                "agent_type": str(agent_type),
                "agent_volume_segment": str(segment),
                "synthetic_latitude": round(float(lat), 5),
                "synthetic_longitude": round(float(lon), 5),
                "base_daily_cash_out": round(float(base_out), 2),
                "cash_in_ratio": round(float(in_ratio), 4),
                "market_day": int(rng.integers(0, 7)) if cluster == "rural" else -1,
                "target_cash_level": float(round(base_out * provisioning / 500.0) * 500.0),
                "target_efloat_level": float(round(base_out * 0.9 / 500.0) * 500.0),
            })
            idx += 1
    return pd.DataFrame(rows)


def _inject_anomalies(rng, n_agents, n_hours, ts, demo_window_start_idx):
    """Return (label, type, multipliers) arrays of shape (n_hours, n_agents)."""
    label = np.zeros((n_hours, n_agents), dtype=np.int8)
    a_type = np.full((n_hours, n_agents), "", dtype=object)
    out_m = np.ones((n_hours, n_agents))
    in_m = np.ones((n_hours, n_agents))
    cnt_m = np.ones((n_hours, n_agents))
    night_add = np.zeros((n_hours, n_agents))
    hours_of_day = ts.hour.to_numpy()

    episodes = []
    n_random = 420
    for _ in range(n_random):
        episodes.append((int(rng.integers(0, n_agents)), int(rng.integers(24, n_hours - 8)),
                         str(rng.choice(ANOMALY_TYPES))))
    # A few scheduled episodes inside the final 30 hours so the dashboard's demo
    # window contains labelled anomalies (documented in docs/DATA_CARD.md).
    for k, t in enumerate(ANOMALY_TYPES * 2):
        episodes.append((int(rng.integers(0, n_agents)), demo_window_start_idx + 3 * k + 1, t))

    for agent, start, kind in episodes:
        if kind == "odd_hour":
            # move to the nearest 01:00-04:00 night window
            day_start = start - hours_of_day[start]
            start = min(day_start + int(rng.integers(1, 4)), n_hours - 3)
            dur = int(rng.integers(1, 3))
        else:
            if hours_of_day[start] < 9 or hours_of_day[start] > 20:
                start = start - hours_of_day[start] + int(rng.integers(10, 19))
            dur = int(rng.integers(2, 5)) if kind in ("rapid_burst", "cash_churn") else int(rng.integers(1, 3))
        sl = slice(start, min(start + dur, n_hours))
        label[sl, agent] = 1
        a_type[sl, agent] = kind
        if kind == "rapid_burst":
            cnt_m[sl, agent] *= rng.uniform(4.0, 6.5)
            out_m[sl, agent] *= rng.uniform(1.6, 2.4)
        elif kind == "large_ticket":
            out_m[sl, agent] *= rng.uniform(2.6, 3.8)
            cnt_m[sl, agent] *= 0.6
        elif kind == "odd_hour":
            night_add[sl, agent] = rng.uniform(0.06, 0.12)  # share of daily volume at night
        elif kind == "cash_churn":
            out_m[sl, agent] *= rng.uniform(2.6, 3.6)
            in_m[sl, agent] *= rng.uniform(2.6, 3.6)
            cnt_m[sl, agent] *= rng.uniform(1.8, 2.6)
    return label, a_type, out_m, in_m, cnt_m, night_add


def simulate_cash(out_req, cash_in, target_cash, hours_of_day, initial_cash=None,
                  transfers=None):
    """Simulate the agent cash drawer under the manual daily-reset policy.

    out_req, cash_in: (n_hours, n_agents) requested cash-out and cash-in amounts.
    transfers: optional (n_hours, n_agents) cash added (+) / removed (-) at the start of an hour.
    Returns (cash_end, served, unmet), each (n_hours, n_agents).
    """
    n_hours, n_agents = out_req.shape
    cash = np.array(target_cash if initial_cash is None else initial_cash, dtype=float).copy()
    cash_end = np.empty((n_hours, n_agents))
    served = np.empty((n_hours, n_agents))
    unmet = np.empty((n_hours, n_agents))
    for t in range(n_hours):
        if hours_of_day[t] == OPENING_HOUR:
            cash = np.array(target_cash, dtype=float).copy()
        if transfers is not None:
            cash = cash + transfers[t]
        available = cash + cash_in[t]
        s = np.minimum(out_req[t], available)
        served[t] = s
        unmet[t] = out_req[t] - s
        cash = available - s
        cash_end[t] = cash
    return cash_end, served, unmet


def generate(seed: int = config.SEED, n_agents: int = config.N_AGENTS,
             n_days: int = config.N_DAYS, start: pd.Timestamp = config.START) -> GeneratedData:
    rng = np.random.default_rng(seed)
    agents = generate_agents(rng, n_agents)
    n_hours = n_days * 24
    ts = pd.date_range(start, periods=n_hours, freq="h")
    hod = ts.hour.to_numpy()
    dow = ts.dayofweek.to_numpy()
    dom = ts.day.to_numpy()
    day_idx = np.arange(n_hours) // 24
    profiles = hour_profiles()

    out_exp = np.empty((n_hours, n_agents))
    in_exp = np.empty((n_hours, n_agents))
    for j, a in agents.iterrows():
        c = a["location_cluster"]
        dowf = DOW_FACTOR[c][dow].copy()
        if a["market_day"] >= 0:
            dowf = np.where(dow == a["market_day"], dowf * 1.45, dowf)
        daily_out = a["base_daily_cash_out"]
        daily_in = daily_out * a["cash_in_ratio"]
        out_exp[:, j] = daily_out * profiles[c]["out"][hod] * dowf * salary_factor(dom, c, "out")
        in_exp[:, j] = daily_in * profiles[c]["in"][hod] * dowf * salary_factor(dom, c, "in")

    # Persistent day-level regimes: AR(1) per agent on log scale.
    day_shock = np.zeros((n_days, n_agents))
    eps = rng.normal(0, 0.10, size=(n_days, n_agents))
    for d in range(1, n_days):
        day_shock[d] = 0.6 * day_shock[d - 1] + eps[d]
    regime = np.exp(day_shock[day_idx])
    # Legitimate temporary demand spikes (local events), ~1 per agent per 10 days.
    spike = np.ones((n_hours, n_agents))
    for _ in range(int(n_agents * n_days / 10)):
        a = int(rng.integers(0, n_agents))
        t0 = int(rng.integers(0, n_hours - 6))
        if 9 <= hod[t0] <= 19:
            spike[t0:t0 + int(rng.integers(2, 6)), a] *= rng.uniform(1.6, 2.6)
    noise_out = rng.lognormal(-0.5 * 0.33 ** 2, 0.33, size=(n_hours, n_agents))
    noise_in = rng.lognormal(-0.5 * 0.33 ** 2, 0.33, size=(n_hours, n_agents))

    demo_window_start = n_hours - 30
    label, a_type, out_m, in_m, cnt_m, night_add = _inject_anomalies(
        rng, n_agents, n_hours, ts, demo_window_start)

    base_daily = agents["base_daily_cash_out"].to_numpy()[None, :]
    cash_out = out_exp * regime * spike * noise_out * out_m + night_add * base_daily
    cash_in = in_exp * regime * noise_in * in_m + 0.5 * night_add * base_daily
    cash_out = np.round(cash_out, -1)
    cash_in = np.round(cash_in, -1)

    clusters = agents["location_cluster"].to_numpy()
    out_ticket = np.array([OUT_TICKET[c] for c in clusters])[None, :]
    in_ticket = np.array([IN_TICKET[c] for c in clusters])[None, :]
    out_cnt = rng.poisson(cash_out / out_ticket * cnt_m)
    in_cnt = rng.poisson(cash_in / in_ticket * np.where(a_type == "cash_churn", cnt_m, 1.0))
    activity = (cash_out + cash_in) / (out_ticket + in_ticket)
    send_cnt = rng.poisson(0.9 * activity)
    pay_cnt = rng.poisson(0.6 * activity)

    target_cash = agents["target_cash_level"].to_numpy()
    cash_end, served, unmet = simulate_cash(cash_out, cash_in, target_cash, hod)

    # e-float moves opposite to cash (agent receives e-money when paying cash out).
    target_ef = agents["target_efloat_level"].to_numpy()
    ef = np.empty((n_hours, n_agents))
    e = target_ef.copy()
    for t in range(n_hours):
        if hod[t] == OPENING_HOUR:
            e = target_ef.copy()
        e = np.maximum(e + served[t] - cash_in[t], 0.0)
        ef[t] = e

    n = n_hours * n_agents
    txn_cnt = out_cnt + in_cnt + send_cnt + pay_cnt
    cash_txn = np.maximum(out_cnt + in_cnt, 1)
    hourly = pd.DataFrame({
        "agent_id": np.tile(agents["agent_id"].to_numpy(), n_hours),
        "timestamp": np.repeat(ts.to_numpy(), n_agents),
        "cash_balance": cash_end.ravel().round(2),
        "efloat_balance": ef.ravel().round(2),
        "cash_in_count": in_cnt.ravel().astype(np.int32),
        "cash_in_amount": cash_in.ravel(),
        "cash_out_count": out_cnt.ravel().astype(np.int32),
        # requested cash-out demand (served + declined/unmet attempts)
        "cash_out_amount": cash_out.ravel(),
        "cash_out_served": served.ravel().round(2),
        "unmet_cash_out": unmet.ravel().round(2),
        "send_money_count": send_cnt.ravel().astype(np.int32),
        "payment_count": pay_cnt.ravel().astype(np.int32),
        "transaction_count": txn_cnt.ravel().astype(np.int32),
        "average_transaction_value": ((cash_out + cash_in) / cash_txn).ravel().round(2),
        "hour": np.repeat(hod, n_agents).astype(np.int8),
        "day_of_week": np.repeat(dow, n_agents).astype(np.int8),
        "is_weekend": np.repeat(np.isin(dow, [4, 5]), n_agents),
        "is_salary_period": np.repeat(is_salary_period(dom), n_agents),
        "liquidity_shortage": (unmet.ravel() > 0).astype(np.int8),
        "known_anomaly_label": label.ravel(),
        "anomaly_type": a_type.ravel().astype(str),
    })
    assert len(hourly) == n
    hourly = hourly.sort_values(["agent_id", "timestamp"], kind="stable").reset_index(drop=True)
    return GeneratedData(agents=agents, hourly=hourly)


def save(data: GeneratedData) -> None:
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    data.agents.to_parquet(config.AGENTS_PATH, index=False)
    data.hourly.to_parquet(config.DATASET_PATH, index=False)


def load() -> GeneratedData:
    return GeneratedData(agents=pd.read_parquet(config.AGENTS_PATH),
                         hourly=pd.read_parquet(config.DATASET_PATH))
