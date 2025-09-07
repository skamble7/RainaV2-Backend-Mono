# app/graphs/guidance_graph.py
import time
from typing import List, Dict, Any, Optional
from datetime import datetime
import logging
import re

from app.models.schemas import GuidanceDocument, GuidanceSection
from app.clients.artifact_client import ArtifactClient
from app.agents.guidance_agent import run_agent
from app.infra.pdf import markdown_to_pdf
from app.infra.storage import path_for, images_dir_for_workspace, rel_to_output
from app.infra.drawio import render_drawio_xml_to_png
from app.config import settings
from app.models.events import GuidanceGeneratedEvent
from app.dal.guidance_doc_dal import next_version_for, insert_record
from app.infra.rabbit import publish_event_v1

logger = logging.getLogger(__name__)

DRAWIO_KINDS = {
    "cam.diagram.context",
    "cam.diagram.class",
    "cam.diagram.activity",
    "cam.diagram.deployment",
}

def _parse_markdown_to_struct(md: str, sections: List[str]) -> GuidanceDocument:
    def mk_section(sec: str) -> GuidanceSection:
        return GuidanceSection(
            id=sec,
            title=sec.replace("_", " ").title(),
            content_md=f"## {sec}\n\n{md}"
        )
    doc = GuidanceDocument(
        workspace_id="",
        title="Technical Architecture & Design Guidance",
        **{sec: mk_section(sec) for sec in sections}
    )
    return doc

def _safe_filename_component(name: str) -> str:
    name = (name or "").strip()
    if not name:
        return "workspace"
    return "".join(ch if re.match(r"[A-Za-z0-9_.-]", ch) else "_" for ch in name)

def _collect_and_render_diagrams(
    *,
    artifacts_all: List[Dict[str, Any]],
    workspace_name: str,
    drawio_bin: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Find drawio artifacts, render to images/<workspace_name>/...png,
    and return an assets descriptor list for the agent.
    """
    safe_ws = _safe_filename_component(workspace_name)
    out_dir = images_dir_for_workspace(safe_ws)
    assets: List[Dict[str, Any]] = []
    counters: Dict[str, int] = {}

    for a in artifacts_all or []:
        kind = a.get("kind")
        if kind not in DRAWIO_KINDS:
            continue

        data = a.get("data") or {}
        xml = data.get("instructions") or ""
        if not xml:
            continue

        counters[kind] = counters.get(kind, 0) + 1
        idx = counters[kind]

        base_name = _safe_filename_component(f"{kind.split('.')[-1]}_{idx}")
        out_png = out_dir / f"{base_name}.png"
        ok = render_drawio_xml_to_png(xml, out_png, drawio_bin=drawio_bin)

        rel_png = str(rel_to_output(out_png)) if ok else None
        assets.append({
            "artifact_id": a.get("artifact_id") or a.get("_id") or a.get("id"),
            "kind": kind,
            "name": a.get("name") or base_name,
            "image_path": rel_png,                 # The agent will embed when present
            "note": "Rendered from draw.io mxfile" if ok else "Draw.io CLI not available; image not rendered",
        })

    if assets:
        logger.info("Prepared diagram assets", extra={"count": len(assets), "dir": str(out_dir)})
    return assets

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

    # 1) Fetch the full parent bundle from artifact-service
    ws_bundle = await ac.fetch_workspace_with_artifacts(workspace_id, include_deleted=False)
    workspace_meta = ws_bundle.get("workspace") or {}
    artifacts_raw = ws_bundle.get("artifacts") or []
    inputs_baseline = ws_bundle.get("inputs_baseline") or {}

    # Optional filter for the LLM artifact slice (we still look for diagrams across all)
    if artifact_kinds:
        kinds_set = set(artifact_kinds)
        artifacts = [a for a in artifacts_raw if a.get("kind") in kinds_set]
    else:
        artifacts = artifacts_raw

    # 2) Source IDs for metadata
    source_ids = []
    for a in artifacts_raw:
        sid = a.get("artifact_id") or a.get("id") or a.get("_id")
        if sid:
            source_ids.append(sid)

    # 3) Render draw.io assets to images/...
    workspace_name = workspace_meta.get("name") or workspace_id
    assets = _collect_and_render_diagrams(
        artifacts_all=artifacts_raw,
        workspace_name=workspace_name,
        drawio_bin=getattr(settings, "DRAWIO_BIN", None),
    )

    # 4) Ask LLM for a verbose doc, with assets included
    md = await run_agent(
        artifacts=artifacts,
        sections=sections,
        model_id=model_id,
        temperature=temperature,
        workspace=workspace_meta,
        inputs=inputs_baseline,
        assets=assets,
    )

    # 5) Structure + validate
    doc = _parse_markdown_to_struct(md, sections)
    doc.workspace_id = workspace_id
    doc.metadata = {
        "source_artifact_ids": source_ids,
        "model_id": model_id or settings.LLM_MODEL_ID,
        "sections_requested": sections,
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "inputs_baseline_version": ws_bundle.get("inputs_baseline_version") or 1,
        "assets": assets,
    }
    missing = [s for s in sections if getattr(doc, s) is None]
    doc.metadata["validation"] = {"missing_sections": missing}

    filename_md: Optional[str] = None
    filename_pdf: Optional[str] = None
    file_path_md: Optional[str] = None
    file_path_pdf: Optional[str] = None
    version: Optional[int] = None

    # 6) Persist to filesystem + DB tracking (unless dry_run)
    if not dry_run:
        version = await next_version_for(workspace_id)
        safe_ws = _safe_filename_component(workspace_name)

        # Write Markdown
        filename_md = f"{safe_ws}_v{version}.md"
        p_md = path_for(filename_md)
        with open(p_md, "w", encoding="utf-8") as f:
            f.write(md)
        file_path_md = str(p_md)

        # Optional PDF (resolve images via base_dir=OUTPUT_DIR)
        if include_pdf:
            filename_pdf = f"{safe_ws}_v{version}.pdf"
            p_pdf = path_for(filename_pdf)
            markdown_to_pdf(md, p_pdf)  # base_dir defaults to OUTPUT_DIR inside function
            file_path_pdf = str(p_pdf)

        # DB record
        await insert_record(
            workspace_id=workspace_id,
            workspace_name=workspace_name,
            filename_md=filename_md,
            filename_pdf=filename_pdf,
            version=version,
            sections=sections,
            meta={
                "model_id": model_id or settings.LLM_MODEL_ID,
                "source_artifact_ids": source_ids,
                "assets": assets,
            },
        )

        # 7) Event
        evt = GuidanceGeneratedEvent(
            workspace_id=workspace_id,
            workspace_name=workspace_name,
            version=version,
            filename_md=filename_md,
            filename_pdf=filename_pdf,
            source_artifact_ids=source_ids,
            model_id=model_id or settings.LLM_MODEL_ID,
            duration_ms=int((time.time() - t0) * 1000),
            meta={"sections": sections},
        ).dict()

        await publish_event_v1(
            event="generated",
            org=getattr(settings, "EVENTS_ORG", "raina"),
            payload=evt,
        )

    return {
        "document": doc,
        "workspace_name": workspace_name,
        "version": version,
        "filename_md": filename_md,
        "filename_pdf": filename_pdf,
        "file_path_md": file_path_md,
        "file_path_pdf": file_path_pdf,
    }
