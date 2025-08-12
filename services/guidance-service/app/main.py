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

# --- Correlation middleware & logging filter ---
# Ensure you have app/middleware/correlation.py as suggested earlier.
# (If not, create it using the snippet I shared for CorrelationIdMiddleware/Filter.)
from app.middleware.correlation import (
    CorrelationIdMiddleware,
    CorrelationIdFilter,
)

# Initialize logging early
setup_logging()

# Add correlation filter to common loggers
_corr_filter = CorrelationIdFilter()
for _name in ("", "uvicorn.access", "uvicorn.error", "app"):
    logging.getLogger(_name).addFilter(_corr_filter)

logger = logging.getLogger("app.main")

app = FastAPI(title="guidance-service", version="0.1.0")

# Apply middleware so every request gets request/correlation IDs
app.add_middleware(CorrelationIdMiddleware)


@app.get("/healthz")
async def health():
    return {"status": "ok", "service": settings.SERVICE_NAME}


@app.post("/guidance/generate", response_model=GuidanceGenerateResponse)
async def generate(req: GuidanceGenerateRequest):
    """
    Kicks off the guidance pipeline. Correlation middleware will:
      - Attach x-request-id and x-correlation-id to the response headers
      - Enrich logs with request_id/correlation_id automatically
    """
    sections = req.sections or settings.DEFAULT_SECTIONS

    # Optional: structured log to help trace calls (IDs added by the filter)
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

    result = await run_guidance_pipeline(
        workspace_id=req.workspace_id,
        artifact_kinds=req.artifact_kinds,
        sections=sections,
        model_id=req.model_id,
        temperature=req.temperature,
        dry_run=req.dry_run,
        include_pdf=req.include_pdf,
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


@app.get("/guidance/{artifact_id}/download")
async def download_pdf(artifact_id: str):
    path = pdf_path_for(artifact_id)  # -> /output/<artifact_id>.pdf
    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"PDF not found at {path}. Re-generate with include_pdf=true.",
        )
    return FileResponse(path, filename=f"{artifact_id}.pdf", media_type="application/pdf")


# (Optional: keep a workspace-scoped variant for consistency)
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
        port=int(getattr(settings, "PORT", 8013)),
        reload=getattr(settings, "DEBUG", False),
        log_level="info",
    )
