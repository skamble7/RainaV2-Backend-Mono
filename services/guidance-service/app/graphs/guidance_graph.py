import time
from typing import List, Dict, Any
from app.models.state import GuidanceState
from app.models.schemas import GuidanceDocument, GuidanceSection
from app.clients.artifact_client import ArtifactClient
from app.agents.guidance_agent import run_agent
from app.infra.rabbit import RabbitPublisher
from app.infra.pdf import markdown_to_pdf
from app.infra.storage import pdf_path_for
from app.config import settings
from app.models.events import GuidanceGeneratedEvent

def _parse_markdown_to_struct(md: str, sections: List[str]) -> GuidanceDocument:
    # Very light structuring: split by headers; in practice you'd use
    # a structured JSON output instruction or JSON mode.
    def mk_section(sec: str) -> GuidanceSection:
        return GuidanceSection(id=sec, title=sec.replace("_"," ").title(), content_md=f"## {sec}\n\n" + md)

    doc = GuidanceDocument(
        workspace_id="",
        title="Technical Architecture & Design Guidance",
        **{sec: mk_section(sec) for sec in sections}
    )
    return doc

async def run_guidance_pipeline(
    workspace_id: str,
    artifact_kinds: List[str] | None,
    sections: List[str],
    model_id: str | None,
    temperature: float | None,
    dry_run: bool,
    include_pdf: bool
):
    t0 = time.time()
    ac = ArtifactClient()
    pub = RabbitPublisher()

    # 1) fetch artifacts
    artifacts = await ac.fetch_cam_artifacts(workspace_id, artifact_kinds)
    source_ids = [a.get("id") for a in artifacts if a.get("id")]

    # 2) generate (LLM)
    md = await run_agent(artifacts, sections, model_id, temperature)

    # 3) structure + validate
    doc = _parse_markdown_to_struct(md, sections)
    doc.workspace_id = workspace_id
    doc.metadata = {
        "source_artifact_ids": source_ids,
        "model_id": model_id or settings.LLM_MODEL_ID,
        "sections_requested": sections,
    }

    # simple completeness check
    missing = [s for s in sections if getattr(doc, s) is None]
    doc.metadata["validation"] = {"missing_sections": missing}

    artifact_id = None
    pdf_path = None

    # 4) persist + optional PDF
    if not dry_run:
        artifact_id = await ac.persist_document(workspace_id, doc.dict())
        if include_pdf:
            out = pdf_path_for(artifact_id)
            markdown_to_pdf(md, out)
            pdf_path = str(out)

        # 5) publish event
        evt = GuidanceGeneratedEvent(
            document_artifact_id=artifact_id,
            workspace_id=workspace_id,
            source_artifact_ids=source_ids,
            model_id=doc.metadata["model_id"],
            duration_ms=int((time.time()-t0)*1000),
            meta={"sections": sections}
        ).dict()
        await pub.publish("guidance.generated", evt)

    return {
        "document": doc,
        "artifact_id": artifact_id,
        "pdf_path": pdf_path
    }
