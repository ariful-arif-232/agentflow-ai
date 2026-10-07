"""Provider-neutral transaction-feed contract and a deterministic stream/replay adapter.

Synthetic integration evidence — not a real upay integration. This module shows how an MFS provider
could feed AgentFlow without any customer data, and proves that feeding the existing synthetic data
through that contract, hour by hour, reproduces the decision snapshots of the existing batch pipeline.

Contract (``agentflow.feed.v1``)
--------------------------------
* ``AgentRecord`` — slow-changing agent reference data (registry): synthetic ID, district, location
  cluster, volume segment, agent type, outlet coordinates, weekly market day and the agent's standard
  morning cash level. No owner, phone or national-ID fields.
* ``FeedEvent`` — one **aggregated** record per agent per hour: closing cash and e-float balances,
  cash-in / cash-out counts and amounts (requested and served cash-out), send-money / payment counts and
  the total transaction count. No customer identifiers, no individual transactions.

Validation is strict: unknown fields are rejected (so an MSISDN or name cannot be smuggled in), names
that look like personal data are rejected even if the schema is extended, timestamps must be hour-aligned,
amounts finite and non-negative, counts non-negative integers, served cash-out ≤ requested, and the
total count ≥ the sum of its parts. A batch must not repeat an (agent, hour) pair.

Mapping into AgentFlow inputs
-----------------------------
``to_hourly_frame`` turns validated events into exactly the columns ``features.build_features`` reads:
``cash_out_amount`` = requested cash-out, ``cash_out_served`` = served, ``unmet_cash_out`` = requested −
served, ``average_transaction_value`` = (cash-in + cash-out) ÷ max(cash-in + cash-out count, 1), and the
calendar fields (hour, weekday, Bangladesh weekend Fri–Sat, salary period, shortage flag) derived from the
timestamp. Ground-truth anomaly labels exist only in the synthetic generator and are not part of a feed.

Replay adapter
--------------
``ReplayFeed`` emits the held-out dataset as hourly batches in chronological order. ``StreamingDecisionAdapter``
ingests batches, keeps a bounded rolling window (``WINDOW_HOURS``) plus running per-agent training-period
shortage counts, and on request builds the decision snapshot with the unchanged feature code, forecast
models, anomaly detector and risk formula.
"""
from __future__ import annotations

import re
from collections import deque
from datetime import datetime
from typing import Literal

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from . import config, data_gen, engine, features

SCHEMA_VERSION = "agentflow.feed.v1"
LABEL = "Synthetic integration and benchmark evidence — not real upay production performance or a real upay integration."
# Rolling window the decision path needs: 168-h rolling statistics and 7-day same-hour lags on 3-h
# sums (171 h) plus margin; equals the serving engine's 9-day history.
WINDOW_HOURS = engine.SERVING_HISTORY_DAYS * 24
PII_PATTERN = re.compile(r"(msisdn|phone|mobile|nid|national|passport|customer|name|email|address|account|dob|birth)",
                         re.IGNORECASE)
FEED_COLUMNS = ("cash_balance", "efloat_balance", "cash_in_count", "cash_in_amount", "cash_out_count",
                "cash_out_amount", "cash_out_served", "unmet_cash_out", "send_money_count", "payment_count",
                "transaction_count")

NonNegFloat = Field(ge=0, allow_inf_nan=False)
NonNegInt = Field(ge=0, strict=True)


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="before")
    @classmethod
    def _no_pii_like_fields(cls, data):
        if isinstance(data, dict):
            bad = [k for k in data if PII_PATTERN.search(str(k)) and k not in cls.model_fields]
            if bad:
                raise ValueError(f"fields that look like personal data are not accepted: {sorted(bad)}")
        return data


class AgentRecord(_Strict):
    """Agent reference data (registry). Coordinates are the outlet location, never a customer's."""
    agent_id: str = Field(pattern=r"^AG-\d{4,6}$")
    district: str = Field(min_length=1, max_length=40)
    location_cluster: Literal["urban_core", "urban_periphery", "rural"]
    agent_volume_segment: Literal["low", "medium", "high"]
    agent_type: str = Field(min_length=1, max_length=40)
    outlet_latitude: float = Field(ge=20.0, le=27.0, allow_inf_nan=False)    # Bangladesh bounding box
    outlet_longitude: float = Field(ge=88.0, le=93.0, allow_inf_nan=False)
    market_day: int = Field(ge=-1, le=6, strict=True)                       # -1 = none, 0 = Monday
    standard_morning_cash_bdt: float = NonNegFloat


class FeedEvent(_Strict):
    """One aggregated agent-hour. Amounts in BDT; counts are numbers of transactions in the hour."""
    schema_version: Literal["agentflow.feed.v1"] = SCHEMA_VERSION
    agent_id: str = Field(pattern=r"^AG-\d{4,6}$")
    hour_start: datetime
    closing_cash_bdt: float = NonNegFloat
    closing_efloat_bdt: float = NonNegFloat
    cash_in_count: int = NonNegInt
    cash_in_amount_bdt: float = NonNegFloat
    cash_out_count: int = NonNegInt
    cash_out_requested_bdt: float = NonNegFloat
    cash_out_served_bdt: float = NonNegFloat
    send_money_count: int = NonNegInt
    payment_count: int = NonNegInt
    transaction_count: int = NonNegInt

    @field_validator("hour_start")
    @classmethod
    def _hour_aligned(cls, v: datetime) -> datetime:
        if v.tzinfo is not None:
            raise ValueError("hour_start must be local time (Asia/Dhaka) without a UTC offset")
        if v.minute or v.second or v.microsecond:
            raise ValueError("hour_start must be aligned to the start of an hour")
        return v

    @model_validator(mode="after")
    def _consistent(self):
        if self.cash_out_served_bdt > self.cash_out_requested_bdt + 1e-6:
            raise ValueError("cash_out_served_bdt cannot exceed cash_out_requested_bdt")
        if self.transaction_count < self.cash_in_count + self.cash_out_count + self.send_money_count + self.payment_count:
            raise ValueError("transaction_count must be at least the sum of its components")
        return self


def json_schema() -> dict:
    return {"schema_version": SCHEMA_VERSION, "agent_record": AgentRecord.model_json_schema(),
            "feed_event": FeedEvent.model_json_schema()}


def validate_batch(events: list[dict]) -> list[FeedEvent]:
    """Validate one hourly batch; raises ValueError listing the first problems (no partial ingestion)."""
    out, errors, seen = [], [], set()
    for i, e in enumerate(events):
        try:
            ev = FeedEvent.model_validate(e)
        except ValidationError as exc:
            errors.append(f"event {i}: {exc.errors()[0]['msg']}")
            continue
        key = (ev.agent_id, ev.hour_start)
        if key in seen:
            errors.append(f"event {i}: duplicate agent-hour {ev.agent_id} {ev.hour_start}")
        seen.add(key)
        out.append(ev)
    if errors:
        raise ValueError(f"{len(errors)} invalid event(s): " + "; ".join(errors[:5]))
    return out


def to_hourly_frame(events: list[FeedEvent]) -> pd.DataFrame:
    """Map validated events onto the hourly columns the existing feature pipeline reads."""
    df = pd.DataFrame({
        "agent_id": [e.agent_id for e in events],
        "timestamp": pd.to_datetime([e.hour_start for e in events]),
        "cash_balance": [e.closing_cash_bdt for e in events],
        "efloat_balance": [e.closing_efloat_bdt for e in events],
        "cash_in_count": np.array([e.cash_in_count for e in events], dtype=np.int32),
        "cash_in_amount": [e.cash_in_amount_bdt for e in events],
        "cash_out_count": np.array([e.cash_out_count for e in events], dtype=np.int32),
        "cash_out_amount": [e.cash_out_requested_bdt for e in events],
        "cash_out_served": [e.cash_out_served_bdt for e in events],
        "send_money_count": np.array([e.send_money_count for e in events], dtype=np.int32),
        "payment_count": np.array([e.payment_count for e in events], dtype=np.int32),
        "transaction_count": np.array([e.transaction_count for e in events], dtype=np.int32),
    })
    df["unmet_cash_out"] = (df["cash_out_amount"] - df["cash_out_served"]).clip(lower=0).round(2)
    cash_txn = np.maximum(df["cash_out_count"] + df["cash_in_count"], 1)
    df["average_transaction_value"] = ((df["cash_out_amount"] + df["cash_in_amount"]) / cash_txn).round(2)
    ts = df["timestamp"]
    df["hour"] = ts.dt.hour.astype(np.int8)
    df["day_of_week"] = ts.dt.dayofweek.astype(np.int8)
    df["is_weekend"] = df["day_of_week"].isin([4, 5])
    df["is_salary_period"] = data_gen.is_salary_period(ts.dt.day.to_numpy())
    df["liquidity_shortage"] = (df["unmet_cash_out"] > 0).astype(np.int8)
    return df


def registry_frame(records: list[AgentRecord]) -> pd.DataFrame:
    return pd.DataFrame({
        "agent_id": [r.agent_id for r in records], "district": [r.district for r in records],
        "location_cluster": [r.location_cluster for r in records], "agent_type": [r.agent_type for r in records],
        "agent_volume_segment": [r.agent_volume_segment for r in records],
        "synthetic_latitude": [r.outlet_latitude for r in records], "synthetic_longitude": [r.outlet_longitude for r in records],
        "market_day": [r.market_day for r in records], "target_cash_level": [r.standard_morning_cash_bdt for r in records],
    })


# ------------------------------------------------------------------ synthetic source → contract
def agents_to_records(agents: pd.DataFrame) -> list[dict]:
    return [{"agent_id": r.agent_id, "district": r.district, "location_cluster": r.location_cluster,
             "agent_volume_segment": r.agent_volume_segment, "agent_type": r.agent_type,
             "outlet_latitude": float(r.synthetic_latitude), "outlet_longitude": float(r.synthetic_longitude),
             "market_day": int(r.market_day), "standard_morning_cash_bdt": float(r.target_cash_level)}
            for r in agents.itertuples()]


def hourly_to_events(rows: pd.DataFrame) -> list[dict]:
    """Synthetic hourly rows → contract payloads (what a provider would send). Labels are dropped."""
    return [{"schema_version": SCHEMA_VERSION, "agent_id": r.agent_id, "hour_start": r.timestamp.to_pydatetime(),
             "closing_cash_bdt": float(r.cash_balance), "closing_efloat_bdt": float(r.efloat_balance),
             "cash_in_count": int(r.cash_in_count), "cash_in_amount_bdt": float(r.cash_in_amount),
             "cash_out_count": int(r.cash_out_count), "cash_out_requested_bdt": float(r.cash_out_amount),
             "cash_out_served_bdt": float(r.cash_out_served), "send_money_count": int(r.send_money_count),
             "payment_count": int(r.payment_count), "transaction_count": int(r.transaction_count)}
            for r in rows.itertuples()]


class ReplayFeed:
    """Deterministic chronological replay of a synthetic hourly dataset as contract batches."""

    def __init__(self, hourly: pd.DataFrame, start: pd.Timestamp | None = None, end: pd.Timestamp | None = None):
        h = hourly
        if start is not None:
            h = h[h["timestamp"] >= start]
        if end is not None:
            h = h[h["timestamp"] <= end]
        self._h = h.sort_values(["timestamp", "agent_id"], kind="stable")
        self.hours = pd.DatetimeIndex(self._h["timestamp"].unique())

    def __iter__(self):
        for ts, rows in self._h.groupby("timestamp", sort=True):
            yield pd.Timestamp(ts), hourly_to_events(rows)


class StreamingDecisionAdapter:
    """Consumes hourly contract batches and produces AgentFlow decision snapshots on demand."""

    def __init__(self, registry: list[dict], bundle, detector, window_hours: int = WINDOW_HOURS):
        recs = [AgentRecord.model_validate(r) for r in registry]
        self.registry = registry_frame(recs)
        self._known = set(self.registry["agent_id"])
        self.bundle, self.detector = bundle, detector
        self.window_hours = window_hours
        self._window: deque[pd.DataFrame] = deque()
        self._short = pd.Series(0.0, index=self.registry["agent_id"])
        self._obs = pd.Series(0.0, index=self.registry["agent_id"])
        self.last_hour: pd.Timestamp | None = None
        self.events_ingested = 0

    def ingest(self, events: list[dict]) -> pd.Timestamp:
        """Validate and ingest one hourly batch (all events must share the same, next hour)."""
        valid = validate_batch(events)
        hours = {e.hour_start for e in valid}
        if len(hours) != 1:
            raise ValueError("a batch must contain exactly one hour")
        ts = pd.Timestamp(hours.pop())
        if self.last_hour is not None and ts <= self.last_hour:
            raise ValueError(f"out-of-order batch {ts} (last ingested {self.last_hour})")
        unknown = {e.agent_id for e in valid} - self._known
        if unknown:
            raise ValueError(f"events for agents missing from the registry: {sorted(unknown)[:5]}")
        frame = to_hourly_frame(valid)
        if ts < config.TEST_START and ts.hour in engine.OPERATING_HOURS:  # running training-period statistic
            self._short = self._short.add(frame.set_index("agent_id")["liquidity_shortage"].astype(float), fill_value=0)
            self._obs = self._obs.add(pd.Series(1.0, index=frame["agent_id"]), fill_value=0)
        self._window.append(frame)
        while len(self._window) > self.window_hours:
            self._window.popleft()
        self.last_hour = ts
        self.events_ingested += len(valid)
        return ts

    def hist_rate(self) -> pd.Series:
        return (self._short / self._obs).dropna()

    def snapshot(self, hist_rate: pd.Series | None = None) -> pd.DataFrame:
        """Decision snapshot at the last ingested hour, via the unchanged engine code path."""
        hourly = pd.concat(list(self._window), ignore_index=True)
        feats = features.build_features(hourly, self.registry)
        eng = engine.Engine(agents=self.registry, feats=feats, bundle=self.bundle, detector=self.detector,
                            hist_rate=self.hist_rate() if hist_rate is None else hist_rate)
        return eng.snapshot(self.last_hour)


SNAPSHOT_COMPARE_COLUMNS = ("cash_balance", "pred_cash_demand_6h", "pred_net_requirement_6h", "pred_net_requirement_p90_6h",
                            "velocity_ratio_3h", "hist_shortage_rate", "risk_score", "expected_shortfall", "anomaly_score")
SNAPSHOT_EXACT_COLUMNS = ("risk_level", "anomaly_status", "review_priority")


def compare_snapshots(a: pd.DataFrame, b: pd.DataFrame) -> dict:
    """Numeric columns within 1e-6 relative tolerance and categorical decisions identical."""
    a = a.set_index("agent_id").sort_index()
    b = b.set_index("agent_id").sort_index()
    if list(a.index) != list(b.index):
        return {"match": False, "reason": "different agents"}
    max_abs = 0.0
    ok = True
    for c in SNAPSHOT_COMPARE_COLUMNS:
        x, y = a[c].astype(float).to_numpy(), b[c].astype(float).to_numpy()
        both_nan = np.isnan(x) & np.isnan(y)
        diff = np.where(both_nan, 0.0, np.abs(x - y))
        if np.isnan(diff).any() or not np.allclose(np.where(both_nan, 0, x), np.where(both_nan, 0, y), rtol=1e-6, atol=1e-6):
            ok = False
        max_abs = max(max_abs, float(np.nanmax(diff)) if len(diff) else 0.0)
    exact = {c: bool((a[c].astype(str) == b[c].astype(str)).all()) for c in SNAPSHOT_EXACT_COLUMNS}
    return {"match": ok and all(exact.values()), "max_abs_numeric_diff": max_abs, "categorical_identical": exact,
            "agents": len(a)}

