# app/main.py
from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends
from fastapi.responses import ORJSONResponse
from pydantic import UUID4
from uuid import uuid4
from datetime import datetime, timezone
import logging

import httpx
import asyncio
import pymongo

from app.config import settings
from app.logging import setup_logging
from app.models.discovery import StartDiscoveryRequest
from app.models.state import DiscoveryState
from app.graphs.discovery_graph import build_graph
from app.infra.rabbit import publish_event

from app.models.discovery import DiscoveryRun
from app.db.discovery_runs import (
    init_indexes, create_discovery_run, get_by_workspace, delete_by_workspace, set_status
)

# --- Correlation middleware & logging filter ----------------------------
from app.middleware.correlation import (
    CorrelationIdMiddleware,
    CorrelationIdFilter,
    request_id_var,
    correlation_id_var,
)

# --- Reserved key protection for logger.extra ----------------------------
_RESERVED = {
    "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
    "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
    "created", "msecs", "relativeCreated", "thread", "threadName", "process",
    "processName", "message", "asctime"
}

def safe_extra(extra: dict) -> dict:
    """Rename reserved logging keys so they don't break LogRecord creation."""
    out = {}
    for k, v in extra.items():
        if k in _RESERVED:
            out[f"ctx_{k}"] = v
        else:
            out[k] = v
    return out

# ------------------------------------------------------------------------
logger = setup_logging()
app = FastAPI(default_response_class=ORJSONResponse, title=settings.SERVICE_NAME)

# Attach middleware to inject/propagate x-request-id and x-correlation-id
app.add_middleware(CorrelationIdMiddleware)

# Add correlation IDs to all log records (root + uvicorn + app)
_corr_filter = CorrelationIdFilter()
for _name in ("", "uvicorn", "uvicorn.access", "uvicorn.error", "app"):
    logging.getLogger(_name).addFilter(_corr_filter)

# Helper to grab current correlation headers for outbound calls
def _corr_headers() -> dict:
    hdrs = {}
    try:
        rid = request_id_var.get()
        cid = correlation_id_var.get()
        if rid:
            hdrs["x-request-id"] = rid
        if cid:
            hdrs["x-correlation-id"] = cid
    except Exception:
        pass
    return hdrs

# ---- DB wiring ----------------------------------------------------------
def get_db():
    client = pymongo.MongoClient(settings.MONGO_URI, tz_aware=True)
    return client[settings.MONGO_DB]

@app.on_event("startup")
def _startup():
    db = get_db()
    init_indexes(db)
    logger.info(
        "Indexes initialized for discovery_runs",
        extra=safe_extra({"service": settings.SERVICE_NAME})
    )

# ---- health -------------------------------------------------------------
@app.get("/health")
async def health():
    return {"ok": True, "service": settings.SERVICE_NAME, "env": settings.ENV}

@app.get("/ready")
async def ready():
    try:
        async with httpx.AsyncClient(timeout=settings.REQUEST_TIMEOUT_S, headers=_corr_headers()) as client:
            await client.get(f"{settings.CAPABILITY_REGISTRY_URL}/health")
            await client.get(f"{settings.ARTIFACT_SERVICE_URL}/health")
    except Exception as e:
        raise HTTPException(503, f"Not ready: {e}")
    return {"ready": True}

# ---- background worker -------------------------------------------------
async def _run_discovery(req: StartDiscoveryRequest, run_id: UUID4):
    start_ts = datetime.now(timezone.utc)
    db = get_db()
    run_graph = build_graph()
    model_id = (req.options.model if req.options else None) or settings.MODEL_ID

    logger.info(
        "discovery.options.received",
        extra=safe_extra({"options": (req.options.model_dump(by_alias=True) if req.options else {})})
    )

    state: DiscoveryState = {
        "workspace_id": str(req.workspace_id),
        "playbook_id": req.playbook_id,
        "model_id": model_id,
        "inputs": req.inputs.model_dump(),
        "options": (req.options.model_dump() if req.options else {}),
        "artifacts": [],
        "logs": [],
        "errors": [],
        "context": {
            "dry_run": bool(req.options and req.options.dry_run),
            "run_id": str(run_id),
        },
    }

    try:
        set_status(db, run_id, "running")
    except Exception:
        logger.exception("Failed to set run status to running", extra=safe_extra({"run_id": str(run_id)}))

    publish_event("discovery.started", str(req.workspace_id), {
        "run_id": str(run_id),
        "playbook_id": req.playbook_id,
        "model_id": model_id,
        "received_at": start_ts.isoformat()
    })

    try:
        result = await run_graph.ainvoke(state)
        completed_at = datetime.now(timezone.utc)
        summary = {
            "run_id": str(run_id),
            "workspace_id": str(req.workspace_id),
            "playbook_id": req.playbook_id,
            "artifact_ids": result.get("context", {}).get("artifact_ids", []),
            "validations": result.get("validations", []),
            "logs": result.get("logs", []),
            "started_at": start_ts.isoformat(),
            "completed_at": completed_at.isoformat(),
            "duration_s": (completed_at - start_ts).total_seconds(),
        }

        set_status(db, run_id, "completed", result_summary=summary, result_artifacts_ref=None)
        publish_event("discovery.completed", str(req.workspace_id), summary)

    except Exception as e:
        logger.exception("discovery_failed", extra=safe_extra({"run_id": str(run_id)}))
        fail_payload = {
            "run_id": str(run_id),
            "error": str(e),
            "logs": state.get("logs", []),
            "errors": state.get("errors", []),
            "artifact_failures": state.get("context", {}).get("artifact_failures", []),
            "started_at": start_ts.isoformat(),
            "failed_at": datetime.now(timezone.utc).isoformat(),
        }
        try:
            set_status(get_db(), run_id, "failed", error=str(e))
        except Exception:
            logger.exception("Failed to set run status to failed", extra=safe_extra({"run_id": str(run_id)}))
        publish_event("discovery.failed", str(req.workspace_id), fail_payload)

# ---- endpoints ----------------------------------------------------------
@app.post("/discover/{workspace_id}", status_code=202)
async def discover(workspace_id: str, req: StartDiscoveryRequest, bg: BackgroundTasks, db=Depends(get_db)):
    if str(req.workspace_id) != workspace_id:
        raise HTTPException(status_code=400, detail="workspace_id in path and body must match")

    if get_by_workspace(db, req.workspace_id):
        raise HTTPException(status_code=409, detail="A discovery run already exists for this workspace.")

    run_id: UUID4 = UUID4(str(uuid4()))
    try:
        _ = create_discovery_run(db, req, run_id)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))

    bg.add_task(_run_discovery, req, run_id)

    return {
        "accepted": True,
        "run_id": str(run_id),
        "workspace_id": workspace_id,
        "playbook_id": req.playbook_id,
        "model_id": (req.options.model if req.options else None) or settings.MODEL_ID,
        "dry_run": bool(req.options and req.options.dry_run),
        "request_id": request_id_var.get(),
        "correlation_id": correlation_id_var.get(),
        "message": "Discovery started; status available via GET /discover/run/{workspace_id}.",
    }

@app.get("/discover/run/{workspace_id}", response_model=DiscoveryRun)
def get_run(workspace_id: UUID4, db=Depends(get_db)):
    run = get_by_workspace(db, workspace_id)
    if not run:
        raise HTTPException(status_code=404, detail="Discovery run not found.")
    return run

@app.delete("/discover/run/{workspace_id}", status_code=204)
def delete_run(workspace_id: UUID4, db=Depends(get_db)):
    ok = delete_by_workspace(db, workspace_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Discovery run not found.")
