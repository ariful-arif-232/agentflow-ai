"""AgentFlow AI — FastAPI service.

Predict. Explain. Rebalance. Decision support only: no endpoint moves money.
"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import Literal, Optional

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from .morning_plan import get_morning_plan
from .schemas import (AgentsResponse, ErrorResponse, HealthResponse, MorningPlanSimulateRequest, ScenarioRequest,
                      SimulateRequest)
from .service import get_service

log = logging.getLogger("agentflow.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    get_service()  # load data + models once at start-up
    yield


app = FastAPI(
    title="AgentFlow AI API",
    version="1.0.0",
    description="Explainable predictive liquidity orchestration for MFS agent networks. "
                "Synthetic data only; recommendations are decision support and approvals only simulate.",
    lifespan=lifespan,
    responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
)

origins = [o.strip() for o in os.getenv("AGENTFLOW_CORS_ORIGINS", "http://localhost:3000").split(",") if o.strip()]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=False,
                   allow_methods=["GET", "POST"], allow_headers=["Content-Type"])


def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message}})


@app.exception_handler(StarletteHTTPException)
async def http_error(_: Request, exc: StarletteHTTPException):
    code = {404: "not_found", 400: "bad_request", 405: "method_not_allowed"}.get(exc.status_code, "http_error")
    return _error(exc.status_code, code, str(exc.detail))


@app.exception_handler(RequestValidationError)
async def validation_error(_: Request, exc: RequestValidationError):
    first = exc.errors()[0] if exc.errors() else {}
    loc = ".".join(str(x) for x in first.get("loc", []) if x != "body")
    return _error(422, "validation_error", f"{loc}: {first.get('msg', 'invalid request')}".strip(": "))


@app.exception_handler(Exception)
async def unhandled_error(_: Request, exc: Exception):
    log.exception("unhandled error")  # stack trace stays in server logs only
    return _error(500, "internal_error", "An internal error occurred.")


def _as_of(as_of: Optional[str]):
    try:
        return get_service().resolve_as_of(as_of)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


AsOf = Query(default=None, max_length=40, description="Decision timestamp (ISO 8601, held-out period)")


@app.get("/health", response_model=HealthResponse)
def health():
    return get_service().health()


@app.get("/api/meta/time")
def time_options():
    return get_service().time_options()


@app.get("/api/overview")
def overview(as_of: Optional[str] = AsOf):
    return get_service().overview(_as_of(as_of))


@app.get("/api/agents", response_model=AgentsResponse)
def agents(
    as_of: Optional[str] = AsOf,
    risk_level: Optional[list[Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]]] = Query(default=None),
    district: Optional[str] = Query(default=None, max_length=40),
    cluster: Optional[Literal["urban_core", "urban_periphery", "rural"]] = None,
    segment: Optional[Literal["low", "medium", "high"]] = None,
    anomaly_status: Optional[list[Literal["NORMAL", "WATCH", "ANOMALOUS"]]] = Query(default=None),
    search: Optional[str] = Query(default=None, max_length=20, pattern=r"^[A-Za-z0-9-]*$"),
    sort: Literal["risk_score", "cash_balance", "pred_cash_demand_6h", "pred_net_requirement_6h",
                  "expected_shortfall", "coverage_ratio", "anomaly_score", "agent_id"] = "risk_score",
    order: Literal["asc", "desc"] = "desc",
):
    return get_service().agents(_as_of(as_of), risk_level, district, cluster, segment, anomaly_status,
                                search, sort, order)


def _agent_id(agent_id: str) -> str:
    import re
    if not re.fullmatch(r"AG-\d{4}", agent_id):
        raise HTTPException(status_code=400, detail="agent_id must look like AG-0001")
    return agent_id


@app.get("/api/agents/{agent_id}")
def agent_detail(agent_id: str, as_of: Optional[str] = AsOf):
    try:
        return get_service().agent_detail(_as_of(as_of), _agent_id(agent_id))
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")


@app.get("/api/agents/{agent_id}/forecast")
def agent_forecast(agent_id: str, as_of: Optional[str] = AsOf):
    try:
        return get_service().agent_forecast(_as_of(as_of), _agent_id(agent_id))
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")


@app.get("/api/rebalancing/recommendations")
def recommendations(as_of: Optional[str] = AsOf, policy: Optional[Literal["v1", "v2"]] = None):
    """Rebalancing plan. ``policy`` defaults to the policy chosen by the held-out deployment rule."""
    return get_service().recommendations(_as_of(as_of), policy)


@app.post("/api/rebalancing/simulate")
def simulate(req: SimulateRequest):
    if not req.ids_valid():
        raise HTTPException(status_code=400, detail="recommendation ids must look like RB-001")
    ids = list(dict.fromkeys(req.recommendation_ids))
    try:
        return get_service().simulate(_as_of(req.as_of), ids, req.reviewer_note, req.policy)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/api/rebalancing/audit")
def audit():
    return {"simulations": get_service().audit_log, "note": "Simulated approvals only — no money is moved."}


@app.post("/api/scenario")
def scenario(req: ScenarioRequest):
    svc = get_service()
    as_of = _as_of(req.as_of)
    if req.district and req.district not in set(svc.engine.agents["district"]):
        raise HTTPException(status_code=400, detail="unknown district")
    return svc.scenario(as_of, req.demand_shock_pct, req.district, req.regional_shock_pct)


@app.get("/api/logistics/assumptions")
def logistics_assumptions():
    """Phase-2 logistics-cost proxy: formula and the synthetic, configurable demo assumptions in use."""
    return get_service().logistics_assumptions()


@app.get("/api/impact")
def impact():
    imp = get_service().impact
    if not imp:
        raise HTTPException(status_code=404, detail="Impact artifact missing - run python ml/scripts/evaluate.py")
    return imp


@app.get("/api/model/metrics")
def model_metrics():
    svc = get_service()
    if not svc.metrics:
        raise HTTPException(status_code=404, detail="Metrics artifact missing - run python ml/scripts/evaluate.py")
    return {"label": "Synthetic held-out evaluation", "metrics": svc.metrics, "training": svc.training,
            "dataset": svc.dataset}


# ---------------------------------------------------------------- Morning Liquidity Plan (proactive, full day)
PlanDate = Query(default=None, max_length=10, pattern=r"^\d{4}-\d{2}-\d{2}$",
                 description="Morning Plan date (YYYY-MM-DD) from /api/morning-plan/dates")


def _morning_plan():
    mp = get_morning_plan()
    if not mp.available:
        raise HTTPException(status_code=404, detail="Morning Plan artifact missing")
    return mp


@app.get("/api/morning-plan/dates")
def morning_plan_dates():
    return _morning_plan().dates_payload()


@app.get("/api/morning-plan")
def morning_plan(date: Optional[str] = PlanDate):
    mp = _morning_plan()
    d = date or mp.default_date
    try:
        return mp.plan(d)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"No Morning Plan for {d}; see /api/morning-plan/dates")


@app.get("/api/morning-plan/evidence")
def morning_plan_evidence():
    ev = get_morning_plan().evidence()
    if len(ev) <= 2:
        raise HTTPException(status_code=404, detail="Morning Plan evidence artifact missing")
    return ev


@app.post("/api/morning-plan/simulate")
def morning_plan_simulate(req: MorningPlanSimulateRequest):
    if not req.reviewer_acknowledged:
        raise HTTPException(status_code=400, detail="reviewer acknowledgement is required before a simulation")
    mp = _morning_plan()
    try:
        return mp.simulate(req.date, req.reviewer_note)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"No Morning Plan for {req.date}")


@app.get("/api/morning-plan/audit")
def morning_plan_audit():
    return {"simulations": get_morning_plan().audit_log, "note": "Simulated Morning Plan approvals only — no money is moved."}
