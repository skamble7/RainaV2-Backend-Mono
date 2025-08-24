# app/main.py
from __future__ import annotations

import logging
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

from app.config import settings
from app.logging import setup_logging
from app.models.schemas import GuidanceGenerateRequest, GuidanceGenerateResponse
from app.graphs.guidance_graph import run_guidance_pipeline
from app.infra.storage import pdf_path_for
from app.clients.artifact_client import ArtifactClient
from app.infra.rabbit import publish_event_v1  # ← versioned events API

# --- Correlation middleware & logging filter ---
from app.middleware.correlation import (
    CorrelationIdMiddleware,
    CorrelationIdFilter,
)

# Optional: direct access to vars for adding IDs to event headers
try:
    from app.middleware.correlation import request_id_var, correlation_id_var  # type: ignore
except Exception:  # pragma: no cover
    request_id_var = correlation_id_var = None  # type: ignore

# Initialize logging early
setup_logging()

# Add correlation filter to common loggers
_corr_filter = CorrelationIdFilter()
for _name in ("", "uvicorn.access", "uvicorn.error", "app"):
    logging.getLogger(_name).addFilter(_corr_filter)

logger = logging.getLogger("app.main")

app = FastAPI(title=settings.SERVICE_NAME, version="0.1.0")

# Apply middleware so every request gets request/correlation IDs
app.add_middleware(CorrelationIdMiddleware)


def _corr_headers() -> dict:
    """Headers to propagate trace IDs on events."""
    hdrs = {}
    try:
        rid = request_id_var.get() if request_id_var else None
        cid = correlation_id_var.get() if correlation_id_var else None
        if rid:
            hdrs["x-request-id"] = rid
        if cid:
            hdrs["x-correlation-id"] = cid
    except Exception:
        pass
    return hdrs


@app.get("/healthz")
async def health():
    return {"status": "ok", "service": settings.SERVICE_NAME}


@app.post("/guidance/generate", response_model=GuidanceGenerateResponse)
async def generate(req: GuidanceGenerateRequest):
    """
    Kicks off the guidance pipeline, publishing:
      - raina.guidance.started.v1
      - raina.guidance.generated.v1 (on success)
      - raina.guidance.failed.v1 (on error)
    """
    sections = req.sections or settings.DEFAULT_SECTIONS

    # Structured start log
    logger.info(
        "guidance.generate.start",
        extra={
            "workspace_id": req.workspace_id,
            "artifact_kinds": req.artifact_kinds,
            "model_id": req.model_id,
            "include_pdf": req.include_pdf,
            "dry_run": req.dry_run,
        },
    )

    # Emit "started"
    await publish_event_v1(
        event="started",
        org=settings.EVENTS_ORG,
        payload={
            "workspace_id": req.workspace_id,
            "artifact_kinds": req.artifact_kinds,
            "sections": sections,
            "model_id": req.model_id,
            "include_pdf": req.include_pdf,
            "dry_run": req.dry_run,
        },
        headers=_corr_headers(),
    )

    try:
        result = await run_guidance_pipeline(
            workspace_id=req.workspace_id,
            artifact_kinds=req.artifact_kinds,
            sections=sections,
            model_id=req.model_id,
            temperature=req.temperature,
            dry_run=req.dry_run,
            include_pdf=req.include_pdf,
        )

        # Emit "generated" (success)
        await publish_event_v1(
            event="generated",
            org=settings.EVENTS_ORG,
            payload={
                "workspace_id": req.workspace_id,
                "artifact_ids": (result.artifacts or []),
                "pdf_artifact_id": result.pdf_artifact_id,
                "sections": sections,
                "model_id": req.model_id,
            },
            headers=_corr_headers(),
        )

        logger.info(
            "guidance.generate.done",
            extra={
                "workspace_id": req.workspace_id,
                "artifact_count": len(result.artifacts or []),
                "pdf_included": bool(result.pdf_artifact_id),
            },
        )
        return result

    except Exception as e:
        logger.exception(
            "guidance.generate.failed",
            extra={"workspace_id": req.workspace_id},
        )

        # Emit "failed"
        await publish_event_v1(
            event="failed",
            org=settings.EVENTS_ORG,
            payload={
                "workspace_id": req.workspace_id,
                "error": str(e),
                "artifact_kinds": req.artifact_kinds,
                "sections": sections,
                "model_id": req.model_id,
            },
            headers=_corr_headers(),
        )
        # Propagate error to caller
        raise


@app.get("/guidance/{artifact_id}/download")
async def download_pdf(artifact_id: str):
    path = pdf_path_for(artifact_id)  # -> /output/<artifact_id>.pdf
    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"PDF not found at {path}. Re-generate with include_pdf=true.",
        )
    return FileResponse(path, filename=f"{artifact_id}.pdf", media_type="application/pdf")


# (Optional: workspace-scoped variant)
@app.get("/guidance/{workspace_id}/{artifact_id}/download")
async def download_pdf_ws(workspace_id: str, artifact_id: str):
    path = pdf_path_for(artifact_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"PDF not found at {path}.")
    return FileResponse(path, filename=f"{artifact_id}.pdf", media_type="application/pdf")


if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=int(getattr(settings, "SERVICE_PORT", 8014)),
        reload=getattr(settings, "DEBUG", False),
        log_level="info",
    )
