"""Read-only monitoring artifact API; no training or data processing on requests."""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter()
ARTIFACT_PATH = Path(__file__).resolve().parents[3] / "ml" / "artifacts" / "model_monitoring.json"


@router.get("/api/model-monitoring")
def model_monitoring():
    try:
        report = json.loads(ARTIFACT_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return JSONResponse(status_code=404, content={"error": {"code": "monitoring_unavailable",
                            "message": "Monitoring artifact missing; run python ml/scripts/model_monitoring.py."}})
    except (OSError, ValueError):
        return JSONResponse(status_code=503, content={"error": {"code": "monitoring_unavailable",
                            "message": "Monitoring artifact cannot be read; no healthy status is assumed."}})
    required = {"version", "label", "reference", "current", "features", "summary", "action", "method"}
    valid = isinstance(report, dict) and required <= report.keys()
    valid = valid and report["version"] == "phase2-monitoring-1" and isinstance(report["features"], list)
    if not valid:
        return JSONResponse(status_code=503, content={"error": {"code": "monitoring_unavailable",
                            "message": "Unsupported monitoring artifact; regenerate before use."}})
    return report
