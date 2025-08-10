from fastapi import FastAPI, HTTPException
from fastapi.responses import ORJSONResponse
from app.config import settings
from app.logging import setup_logging
from app.models.inputs import StartDiscoveryRequest
from app.models.state import DiscoveryState
from app.graphs.discovery_graph import build_graph
from app.infra.rabbit import publish_event
import httpx

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

@app.post("/discover/{workspace_id}")
async def discover(workspace_id: str, req: StartDiscoveryRequest):
    run = build_graph()
    model_id = (req.options.model if req.options else None) or settings.MODEL_ID

    state: DiscoveryState = {
        "workspace_id": workspace_id,
        "playbook_id": req.playbook_id,
        "model_id": model_id,
        "inputs": req.inputs.model_dump(),
        "options": (req.options.model_dump() if req.options else {}),  # <-- add this line
        "artifacts": [],
        "logs": [],
        "errors": [],
        "context": {"dry_run": bool(req.options and req.options.dry_run)}
    }

    publish_event("discovery.started", workspace_id, {"playbook_id": req.playbook_id, "model_id": model_id})

    try:
        result = await run.ainvoke(state)
    except Exception as e:
        logger.exception("discovery_failed")
        publish_event("discovery.failed", workspace_id, {
            "error": str(e),
            "logs": state.get("logs", []),
            "errors": state.get("errors", []),
            "artifact_failures": state.get("context", {}).get("artifact_failures", [])
        })
        raise HTTPException(
            500,
            f"Discovery failed: {e} | node-errors: {state.get('errors', [])} | artifact-failures: {state.get('context', {}).get('artifact_failures', [])}"
        )


    summary = {
        "workspace_id": workspace_id,
        "playbook_id": req.playbook_id,
        "artifact_ids": result.get("context", {}).get("artifact_ids", []),
        "validations": result.get("validations", []),
        "logs": result.get("logs", [])
    }
    return summary
