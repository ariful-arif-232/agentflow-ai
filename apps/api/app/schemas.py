"""Pydantic request / response schemas."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

RiskLevel = Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
AnomalyStatus = Literal["NORMAL", "WATCH", "ANOMALOUS"]


class ErrorBody(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorBody


class HealthResponse(BaseModel):
    status: Literal["ok"]
    models_loaded: bool
    agents: int
    default_as_of: str
    data_label: str


class AgentSummary(BaseModel):
    model_config = ConfigDict(extra="ignore")
    agent_id: str
    district: str
    location_cluster: str
    agent_type: str
    agent_volume_segment: str
    cash_balance: float
    pred_cash_demand_6h: float
    pred_net_requirement_6h: float
    pred_net_requirement_p90_6h: float
    expected_shortfall: float
    expected_surplus: float
    coverage_ratio: Optional[float]
    risk_score: float = Field(ge=0, le=100)
    risk_level: RiskLevel
    anomaly_status: AnomalyStatus
    anomaly_score: float
    review_priority: str
    synthetic_latitude: float
    synthetic_longitude: float


class AgentsResponse(BaseModel):
    as_of: str
    data_label: str
    currency: str
    horizon_hours: int
    count: int
    agents: list[AgentSummary]
    filters: dict


class SimulateRequest(BaseModel):
    """Human-review simulation of intraday rebalancing. Never moves money.

    ``reviewer_acknowledged`` is required and must be true: approval is enforced by the server, not only
    by the dashboard checkbox.
    """
    model_config = ConfigDict(extra="forbid")
    recommendation_ids: list[str] = Field(min_length=1, max_length=100)
    reviewer_acknowledged: bool = Field(strict=True)  # JSON true/false only; "yes" or 1 are rejected
    reviewer_note: Optional[str] = Field(default=None, max_length=500)
    as_of: Optional[str] = Field(default=None, max_length=40)
    policy: Optional[Literal["v1", "v2"]] = None

    def ids_valid(self) -> bool:
        import re
        return all(re.fullmatch(r"RB-\d{3}", i) for i in self.recommendation_ids)


class ScenarioRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    demand_shock_pct: float = Field(default=0.0, ge=-30, le=80)
    district: Optional[str] = Field(default=None, max_length=40)
    regional_shock_pct: float = Field(default=0.0, ge=0, le=100)
    as_of: Optional[str] = Field(default=None, max_length=40)


class MorningPlanSimulateRequest(BaseModel):
    """Human-review simulation of a Morning Liquidity Plan. Never moves money."""
    model_config = ConfigDict(extra="forbid")
    date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$", max_length=10)
    reviewer_acknowledged: bool
    reviewer_note: Optional[str] = Field(default=None, max_length=500)
