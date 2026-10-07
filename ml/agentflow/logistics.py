"""Phase-2 operational logistics-cost proxy, shared by rebalancing V1, V2 and the impact simulator.

Phase 1 costed a peer transfer as ``BDT 150 + BDT 25/km`` (``phase1_simple_cost``). That simple
estimate is kept unchanged so every Phase-1 metric stays auditable. Phase 2 adds a transparent,
component-based proxy:

    billable_km        = one-way distance_km × distance_multiplier         (round trip by default)
    distance_cost      = billable_km × per_km_operating_cost_bdt
    travel_time_min    = billable_km / average_field_speed_kmh × 60
    time_cost          = (travel_time_min + handling_time_min) / 60 × field_officer_cost_per_hour_bdt
    cash_in_transit    = transferred_amount × cash_in_transit_bps / 10,000
    total              = base_handling + distance_cost + time_cost + cash_in_transit

Every component is rounded to 2 decimals and the total is the sum of the rounded components, so
the parts always add up exactly to the total.

**Every default below is a synthetic, illustrative demo assumption — not a measured upay or
distributor rate.** All values live in one ``LogisticsCostConfig`` and can be overridden with
``AGENTFLOW_LOGISTICS_<FIELD>`` environment variables (numbers only, no secrets), so governed
operator rates can replace them later without code changes.

Distributor replenishment (escalated need) uses the district centroid of the synthetic data
generator as a *synthetic distributor-hub proxy*. No real distributor location is implied.
"""
from __future__ import annotations

import math
import os
from dataclasses import asdict, dataclass, fields, replace

from . import data_gen

ASSUMPTION_LABEL = "Synthetic operational cost proxy — not upay measured cost"
DEPLOYMENT_NOTE = "Simulated operational-cost proxy — replace assumptions with governed operator rates for deployment."
HUB_ASSUMPTION = ("Synthetic distributor-hub proxy: the district centroid of the synthetic data generator. "
                  "It is not the location of any real upay distributor.")
ENV_PREFIX = "AGENTFLOW_LOGISTICS_"


@dataclass(frozen=True)
class LogisticsCostConfig:
    """Illustrative demo assumptions (synthetic). Override per field via AGENTFLOW_LOGISTICS_<FIELD>."""
    # peer transfer (field officer / courier collects from the donor and delivers to the recipient)
    base_handling_bdt: float = 100.0            # dispatch, paperwork and cash-handling fee per trip
    distance_multiplier: float = 2.0            # 2.0 = round trip back to base
    per_km_operating_cost_bdt: float = 12.0     # vehicle fuel and wear per km
    average_field_speed_kmh: float = 15.0       # congested urban/peri-urban average
    handling_time_minutes: float = 15.0         # counting, verification and hand-over at both ends
    field_officer_cost_per_hour_bdt: float = 250.0
    cash_in_transit_bps: float = 10.0           # exposure/insurance proxy, basis points of the amount moved
    # distributor replenishment (escalated need)
    distributor_base_handling_bdt: float = 150.0
    distributor_distance_multiplier: float = 2.0

    def __post_init__(self) -> None:
        for f in fields(self):
            v = getattr(self, f.name)
            if not isinstance(v, (int, float)) or isinstance(v, bool) or not math.isfinite(v) or v < 0:
                raise ValueError(f"logistics assumption {f.name} must be a finite number >= 0 (got {v!r})")
        if self.average_field_speed_kmh <= 0:
            raise ValueError("average_field_speed_kmh must be > 0")
        if self.distance_multiplier < 1 or self.distributor_distance_multiplier < 1:
            raise ValueError("distance multipliers must be >= 1 (travel is at least one way)")


def config_from_env(env: dict | None = None, base: LogisticsCostConfig | None = None) -> LogisticsCostConfig:
    """Defaults overridden by AGENTFLOW_LOGISTICS_<FIELD> variables. Invalid values raise ValueError."""
    env = os.environ if env is None else env
    base = base or LogisticsCostConfig()
    over = {}
    for f in fields(LogisticsCostConfig):
        raw = env.get(ENV_PREFIX + f.name.upper())
        if raw is not None and str(raw).strip() != "":
            try:
                over[f.name] = float(raw)
            except ValueError as exc:
                raise ValueError(f"{ENV_PREFIX}{f.name.upper()} must be a number") from exc
    return replace(base, **over)


def _check(name: str, value: float) -> float:
    v = float(value)
    if not math.isfinite(v) or v < 0:
        raise ValueError(f"{name} must be a finite number >= 0 (got {value!r})")
    return v


def _breakdown(base_bdt: float, distance_km: float, multiplier: float, amount: float,
               cfg: LogisticsCostConfig) -> dict:
    billable = distance_km * multiplier
    travel_min = billable / cfg.average_field_speed_kmh * 60.0
    parts = {
        "base_handling_bdt": round(base_bdt, 2),
        "distance_cost_bdt": round(billable * cfg.per_km_operating_cost_bdt, 2),
        "time_cost_bdt": round((travel_min + cfg.handling_time_minutes) / 60.0 * cfg.field_officer_cost_per_hour_bdt, 2),
        "cash_in_transit_cost_bdt": round(amount * cfg.cash_in_transit_bps / 10_000.0, 2),
    }
    return {
        "travel_distance_km": round(distance_km, 2),
        "distance_multiplier": multiplier,
        "billable_distance_km": round(billable, 2),
        "travel_time_minutes": round(travel_min, 1),
        "handling_time_minutes": cfg.handling_time_minutes,
        **parts,
        "total_estimated_cost_bdt": round(sum(parts.values()), 2),
        "assumption_label": ASSUMPTION_LABEL,
    }


def transfer_cost(distance_km: float, amount_bdt: float, cfg: LogisticsCostConfig | None = None) -> dict:
    """Cost breakdown of one peer transfer of ``amount_bdt`` over a one-way ``distance_km``."""
    cfg = cfg or DEFAULT_CONFIG
    return _breakdown(cfg.base_handling_bdt, _check("distance_km", distance_km), cfg.distance_multiplier,
                      _check("amount_bdt", amount_bdt), cfg)


def transfer_cost_total(distance_km: float, amount_bdt: float, cfg: LogisticsCostConfig | None = None) -> float:
    return transfer_cost(distance_km, amount_bdt, cfg)["total_estimated_cost_bdt"]


def phase1_simple_cost(distance_km: float, fixed_bdt: float = 150.0, per_km_bdt: float = 25.0) -> float:
    """Phase-1 estimate kept for auditability: fixed + per-km, one way, no time or cash-in-transit."""
    return fixed_bdt + per_km_bdt * _check("distance_km", distance_km)


def district_hub(district: str) -> tuple[float, float] | None:
    """Synthetic distributor-hub proxy = district centroid used by the synthetic data generator."""
    v = data_gen.DISTRICTS.get(district)
    return (float(v[0]), float(v[1])) if v else None


def replenishment_cost(district: str, agent_lat: float | None, agent_lon: float | None, amount_bdt: float,
                       cfg: LogisticsCostConfig | None = None) -> dict:
    """Distributor replenishment proxy for an escalated need. Reports 'unavailable' instead of guessing."""
    from .rebalance import haversine_km

    cfg = cfg or DEFAULT_CONFIG
    amount = _check("amount_bdt", amount_bdt)
    hub = district_hub(district)
    missing = [n for n, v in (("agent_latitude", agent_lat), ("agent_longitude", agent_lon))
               if v is None or not math.isfinite(float(v))]
    if hub is None:
        missing.append("synthetic_district_hub")
    if missing:
        return {"available": False, "unavailable_reason": "missing " + ", ".join(missing),
                "hub_assumption": HUB_ASSUMPTION, "assumption_label": ASSUMPTION_LABEL}
    dist = float(haversine_km(hub[0], hub[1], float(agent_lat), float(agent_lon)))
    return {"available": True, "hub": "synthetic district hub", "hub_assumption": HUB_ASSUMPTION,
            "replenishment_amount_bdt": round(amount, 2),
            **_breakdown(cfg.distributor_base_handling_bdt, dist, cfg.distributor_distance_multiplier, amount, cfg)}


def describe(cfg: LogisticsCostConfig | None = None) -> dict:
    """Assumptions block for API responses and artifacts."""
    cfg = cfg or DEFAULT_CONFIG
    return {
        "assumption_label": ASSUMPTION_LABEL,
        "deployment_note": DEPLOYMENT_NOTE,
        "hub_assumption": HUB_ASSUMPTION,
        "formula": ("total = base handling + billable km × per-km cost + (billable km ÷ speed + handling time) × "
                    "hourly field-officer cost + amount × cash-in-transit bps ÷ 10,000; billable km = one-way km × "
                    "distance multiplier"),
        "phase1_formula": "BDT 150 + BDT 25 per one-way km (Phase-1 estimate, kept for auditability)",
        "override": f"set {ENV_PREFIX}<FIELD> environment variables (numbers only)",
        "assumptions": asdict(cfg),
    }


DEFAULT_CONFIG = config_from_env()
