import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from typing import List
from app.config import settings
from app.logging import setup_logging
from app.models.schemas import GuidanceGenerateRequest, GuidanceGenerateResponse
from app.graphs.guidance_graph import run_guidance_pipeline
from app.infra.storage import pdf_path_for
from app.clients.artifact_client import ArtifactClient

setup_logging()
app = FastAPI(title="guidance-service", version="0.1.0")

@app.get("/healthz")
async def health():
    return {"status": "ok", "service": settings.SERVICE_NAME}

@app.post("/guidance/generate", response_model=GuidanceGenerateResponse)
async def generate(req: GuidanceGenerateRequest):
    sections = req.sections or settings.DEFAULT_SECTIONS
    result = await run_guidance_pipeline(
        workspace_id=req.workspace_id,
        artifact_kinds=req.artifact_kinds,
        sections=sections,
        model_id=req.model_id,
        temperature=req.temperature,
        dry_run=req.dry_run,
        include_pdf=req.include_pdf
    )
    return result

@app.get("/guidance/{artifact_id}/download")
async def download_pdf(artifact_id: str):
    path = pdf_path_for(artifact_id)  # -> /output/<artifact_id>.pdf
    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"PDF not found at {path}. Re-generate with include_pdf=true."
        )
    return FileResponse(path, filename=f"{artifact_id}.pdf", media_type="application/pdf")

# (Optional: keep a workspace-scoped variant for consistency)
@app.get("/guidance/{workspace_id}/{artifact_id}/download")
async def download_pdf_ws(workspace_id: str, artifact_id: str):
    path = pdf_path_for(artifact_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"PDF not found at {path}.")
    return FileResponse(path, filename=f"{artifact_id}.pdf", media_type="application/pdf")
