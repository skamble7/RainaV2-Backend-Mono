# app/main.py (or your router module if you keep routes elsewhere)
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import ORJSONResponse
from app.config import settings
from app.logging import setup_logging
from app.models.inputs import StartDiscoveryRequest
from app.models.state import DiscoveryState
from app.graphs.discovery_graph import build_graph
from app.infra.rabbit import publish_event
import httpx
import asyncio
import uuid
from datetime import datetime, timezone

logger = setup_logging()
app = FastAPI(default_response_class=ORJSONResponse, title=settings.SERVICE_NAME)

@app.get("/health")
async def health():
    return {"ok": True, "service": settings.SERVICE_NAME, "env": settings.ENV}

@app.get("/ready")
async def ready():
    try:
        async with httpx.AsyncClient(timeout=settings.REQUEST_TIMEOUT_S) as client:
            await client.get(f"{settings.CAPABILITY_REGISTRY_URL}/health")
            await client.get(f"{settings.ARTIFACT_SERVICE_URL}/health")
    except Exception as e:
        raise HTTPException(503, f"Not ready: {e}")
    return {"ready": True}


# ---- background worker -------------------------------------------------

async def _run_discovery(workspace_id: str, req: StartDiscoveryRequest, run_id: str):
    start_ts = datetime.now(timezone.utc)
    run = build_graph()
    model_id = (req.options.model if req.options else None) or settings.MODEL_ID

    state: DiscoveryState = {
        "workspace_id": workspace_id,
        "playbook_id": req.playbook_id,
        "model_id": model_id,
        "inputs": req.inputs.model_dump(),
        "options": (req.options.model_dump() if req.options else {}),
        "artifacts": [],
        "logs": [],
        "errors": [],
        "context": {"dry_run": bool(req.options and req.options.dry_run), "run_id": run_id},
    }

    # fire started
    publish_event("discovery.started", workspace_id, {
        "run_id": run_id,
        "playbook_id": req.playbook_id,
        "model_id": model_id,
        "received_at": start_ts.isoformat()
    })

    try:
        result = await run.ainvoke(state)

        summary = {
            "run_id": run_id,
            "workspace_id": workspace_id,
            "playbook_id": req.playbook_id,
            "artifact_ids": result.get("context", {}).get("artifact_ids", []),
            "validations": result.get("validations", []),
            "logs": result.get("logs", []),
            "started_at": start_ts.isoformat(),
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "duration_s": (datetime.now(timezone.utc) - start_ts).total_seconds(),
        }
        publish_event("discovery.completed", workspace_id, summary)

    except Exception as e:
        logger.exception("discovery_failed run_id=%s", run_id)
        publish_event("discovery.failed", workspace_id, {
            "run_id": run_id,
            "error": str(e),
            "logs": state.get("logs", []),
            "errors": state.get("errors", []),
            "artifact_failures": state.get("context", {}).get("artifact_failures", []),
            "started_at": start_ts.isoformat(),
            "failed_at": datetime.now(timezone.utc).isoformat(),
        })


# ---- immediate-ack endpoint --------------------------------------------

@app.post("/discover/{workspace_id}", status_code=202)
async def discover(workspace_id: str, req: StartDiscoveryRequest, bg: BackgroundTasks):
    """
    Immediately accepts the request and runs discovery in the background.
    Emits:
      - discovery.started
      - discovery.completed (or discovery.failed)
    """
    run_id = str(uuid.uuid4())
    # schedule background work
    bg.add_task(_run_discovery, workspace_id, req, run_id)

    # return 202 Accepted with a correlation id
    return {
        "accepted": True,
        "run_id": run_id,
        "workspace_id": workspace_id,
        "playbook_id": req.playbook_id,
        "model_id": (req.options.model if req.options else None) or settings.MODEL_ID,
        "dry_run": bool(req.options and req.options.dry_run),
        "message": "Discovery started; results will be published via events."
    }
