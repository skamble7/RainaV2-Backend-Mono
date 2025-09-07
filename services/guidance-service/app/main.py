# app/main.py
from __future__ import annotations

import logging, os
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

from app.config import settings
from app.logging import setup_logging
from app.models.schemas import (
    GuidanceGenerateRequest, GuidanceGenerateResponse, GuidanceListItem
)
from app.graphs.guidance_graph import run_guidance_pipeline
from app.infra.storage import path_for
from app.infra.rabbit import publish_event_v1  # versioned events API
from app.dal.guidance_doc_dal import (
    ensure_indexes, list_by_workspace, get_by_workspace_and_filename, delete_by_workspace_and_filename
)

# --- Correlation middleware & logging filter ---
from app.middleware.correlation import (
    CorrelationIdMiddleware,
    CorrelationIdFilter,
)

try:
    from app.middleware.correlation import request_id_var, correlation_id_var  # type: ignore
except Exception:  # pragma: no cover
    request_id_var = correlation_id_var = None  # type: ignore

setup_logging()

_corr_filter = CorrelationIdFilter()
for _name in ("", "uvicorn.access", "uvicorn.error", "app"):
    logging.getLogger(_name).addFilter(_corr_filter)

logger = logging.getLogger("app.main")

app = FastAPI(title=settings.SERVICE_NAME, version="0.2.0")
app.add_middleware(CorrelationIdMiddleware)

@app.on_event("startup")
async def _on_startup():
    await ensure_indexes()

def _corr_headers() -> dict:
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
    Generates guidance Markdown (and optional PDF) for a workspace,
    stores files under OUTPUT_DIR, tracks filenames in MongoDB,
    and emits versioned events:
      - raina.guidance.started.v1
      - raina.guidance.generated.v1 (on success)
      - raina.guidance.failed.v1 (on error)
    """
    sections = req.sections or settings.DEFAULT_SECTIONS
    logger.info("guidance.generate.start",
        extra={"workspace_id": req.workspace_id, "artifact_kinds": req.artifact_kinds,
               "model_id": req.model_id, "include_pdf": req.include_pdf, "dry_run": req.dry_run})

    # Emit "started"
    await publish_event_v1(
        event="started",
        org=settings.EVENTS_ORG,
        payload={
            "workspace_id": req.workspace_id,
            "artifact_kinds": req.artifact_kinds,
            "sections": sections,
            "model_id": req.model_id or settings.LLM_MODEL_ID,
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

        resp = GuidanceGenerateResponse(
            document=result["document"],
            workspace_name=result["workspace_name"],
            version=result["version"] or 0,
            filename_md=result["filename_md"],
            filename_pdf=result["filename_pdf"],
            file_path_md=result["file_path_md"],
            file_path_pdf=result["file_path_pdf"],
        )

        logger.info("guidance.generate.done",
            extra={"workspace_id": req.workspace_id,
                   "version": resp.version,
                   "filename_md": resp.filename_md,
                   "filename_pdf": bool(resp.filename_pdf)})

        return resp

    except Exception as e:
        logger.exception("guidance.generate.failed", extra={"workspace_id": req.workspace_id})
        await publish_event_v1(
            event="failed",
            org=settings.EVENTS_ORG,
            payload={
                "workspace_id": req.workspace_id,
                "error": str(e),
                "artifact_kinds": req.artifact_kinds,
                "sections": sections,
                "model_id": req.model_id or settings.LLM_MODEL_ID,
            },
            headers=_corr_headers(),
        )
        raise

# ---- CRUD-ish routes for documents (list, download, delete) ----

@app.get("/guidance/workspace/{workspace_id}/documents", response_model=list[GuidanceListItem])
async def list_documents(workspace_id: str):
    docs = await list_by_workspace(workspace_id)
    items: list[GuidanceListItem] = []
    for d in docs:
        items.append(GuidanceListItem(
            workspace_id=d.get("workspace_id"),
            workspace_name=d.get("workspace_name"),
            version=int(d.get("version", 0)),
            filename_md=d.get("filename_md"),
            filename_pdf=d.get("filename_pdf"),
            created_at=(d.get("created_at") or "").isoformat() if d.get("created_at") else "",
            sections=d.get("sections") or [],
            meta=d.get("meta") or {},
        ))
    return items

@app.get("/guidance/workspace/{workspace_id}/download/{filename}")
async def download_document(workspace_id: str, filename: str):
    rec = await get_by_workspace_and_filename(workspace_id, filename)
    if not rec:
        raise HTTPException(status_code=404, detail="Document not found for this workspace")

    p = path_for(filename)
    if not p.exists():
        raise HTTPException(status_code=404, detail="File not found on disk")
    media = "application/pdf" if filename.lower().endswith(".pdf") else "text/markdown"
    return FileResponse(p, filename=filename, media_type=media)

@app.delete("/guidance/workspace/{workspace_id}/documents/{filename}")
async def delete_document(workspace_id: str, filename: str):
    # remove DB record
    deleted = await delete_by_workspace_and_filename(workspace_id, filename)
    # optional: remove file if present
    p = path_for(filename)
    if p.exists():
        try:
            os.remove(p)
        except Exception:
            pass
    if deleted == 0:
        raise HTTPException(status_code=404, detail="Document not found")
    return {"deleted": True, "filename": filename}

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=int(getattr(settings, "SERVICE_PORT", 8014)),
        reload=getattr(settings, "DEBUG", False),
        log_level="info",
    )
