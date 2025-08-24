# app/routes/artifact_routes.py
from __future__ import annotations

from copy import deepcopy
import logging
from typing import Optional, List, Dict, Any

import jsonpatch
from fastapi import APIRouter, HTTPException, Header, Query, Response, status
from fastapi.responses import ORJSONResponse
from pydantic import BaseModel  # ← must be imported before defining Pydantic models

from ..config import settings
from ..db.mongodb import get_db
from ..events.rabbit import publish_event_v1
from ..dal import artifact_dal as dal
from ..models.artifact import (
    ArtifactItemCreate,
    ArtifactItemReplace,
    ArtifactItemPatchIn,
    WorkspaceArtifactsDoc,
    ArtifactItem,
)
from libs.raina_common.events import Service  # versioned routing (service segment)

# ─────────────────────────────────────────────────────────────
# Logging utils
# ─────────────────────────────────────────────────────────────
_RESERVED = {
    "name", "msg", "args", "levelname", "levelno", "pathname", "filename", "module",
    "exc_info", "exc_text", "stack_info", "lineno", "funcName", "created", "msecs",
    "relativeCreated", "thread", "threadName", "process", "processName", "message", "asctime"
}
def safe_extra(extra: dict) -> dict:
    out = {}
    for k, v in extra.items():
        out[f"ctx_{k}" if k in _RESERVED else k] = v
    return out

logger = logging.getLogger("app.routes.artifact")

router = APIRouter(
    prefix="/artifact",
    tags=["artifact"],
    default_response_class=ORJSONResponse,
)

def _set_event_header(response: Response, published: bool) -> None:
    response.headers["X-Event-Published"] = "true" if published else "false"

def _org() -> str:
    return settings.events_org  # default "raina"

# ─────────────────────────────────────────────────────────────
# Create/Upsert single artifact (versioned + lineage)
# ─────────────────────────────────────────────────────────────
@router.post("/{workspace_id}")
async def upsert_artifact(
    workspace_id: str,
    body: ArtifactItemCreate,
    response: Response,
    run_id: Optional[str] = Header(default=None, alias="X-Run-Id"),
):
    """
    Versioned upsert by natural_key (fallback=kind:name) + fingerprint.
    Returns the final artifact plus an 'op' header: insert|update|noop.
    """
    db = await get_db()

    try:
        art, op = await dal.upsert_artifact(
            db=db,
            workspace_id=workspace_id,
            payload=body,
            prov=body.provenance,
            run_id=run_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("upsert_artifact_failed", extra=safe_extra({"workspace_id": workspace_id, "err": str(e)}))
        raise HTTPException(status_code=500, detail="Artifact upsert failed")

    # Events: created only on insert; updated on update; noop = no event
    published = True
    if op == "insert":
        published = publish_event_v1(org=_org(), service=Service.ARTIFACT, event="created", payload=art.model_dump())
    elif op == "update":
        published = publish_event_v1(org=_org(), service=Service.ARTIFACT, event="updated", payload=art.model_dump())

    response.headers["ETag"] = str(art.version)
    response.headers["X-Op"] = op
    _set_event_header(response, published)

    # 201 for insert, 200 otherwise
    status_code = status.HTTP_201_CREATED if op == "insert" else status.HTTP_200_OK
    return ORJSONResponse(art.model_dump(), status_code=status_code)


# ─────────────────────────────────────────────────────────────
# Batch upsert
# ─────────────────────────────────────────────────────────────
class BatchItems(BaseModel):
    items: List[ArtifactItemCreate]

@router.post("/{workspace_id}/upsert-batch")
async def upsert_batch(
    workspace_id: str,
    payload: BatchItems,
    response: Response,
    run_id: Optional[str] = Header(default=None, alias="X-Run-Id"),
):
    """
    Upsert many artifacts in a single call.
    Returns counts and per-item ops for UI diffing.
    """
    db = await get_db()
    results: List[Dict[str, Any]] = []
    counts = {"insert": 0, "update": 0, "noop": 0, "failed": 0}

    for item in payload.items:
        try:
            art, op = await dal.upsert_artifact(db, workspace_id, item, item.provenance, run_id=run_id)
            if op in counts:
                counts[op] += 1
            results.append({
                "artifact_id": art.artifact_id,
                "natural_key": art.natural_key,
                "op": op,
                "version": art.version
            })
            # emit per-item event (same semantics as single upsert)
            if op == "insert":
                publish_event_v1(org=_org(), service=Service.ARTIFACT, event="created", payload=art.model_dump())
            elif op == "update":
                publish_event_v1(org=_org(), service=Service.ARTIFACT, event="updated", payload=art.model_dump())
        except Exception as e:
            logger.exception("batch_upsert_failed_item", extra=safe_extra({"workspace_id": workspace_id, "err": str(e)}))
            counts["failed"] += 1
            results.append({"error": str(e)})

    summary = {"counts": counts, "results": results}
    response.headers["X-Batch-Inserted"] = str(counts["insert"])
    response.headers["X-Batch-Updated"] = str(counts["update"])
    response.headers["X-Batch-Noop"] = str(counts["noop"])
    response.headers["X-Batch-Failed"] = str(counts["failed"])
    return summary


# ─────────────────────────────────────────────────────────────
# Baseline inputs (NEW)
# ─────────────────────────────────────────────────────────────
class InputsBaselineIn(BaseModel):
    avc: Dict[str, Any]
    fss: Dict[str, Any]
    pss: Dict[str, Any]

class InputsBaselinePatch(BaseModel):
    avc: Optional[Dict[str, Any]] = None
    pss: Optional[Dict[str, Any]] = None
    fss_stories_upsert: Optional[List[Dict[str, Any]]] = None

@router.post("/{workspace_id}/baseline-inputs")
async def set_baseline_inputs(
    workspace_id: str,
    body: InputsBaselineIn,
    response: Response,
    if_absent_only: bool = Query(default=False),
    expected_version: Optional[int] = Query(default=None, ge=1),
):
    """
    Set/replace the entire baseline inputs for a workspace.
    - if_absent_only: only set if currently empty (first capture)
    - expected_version: optional optimistic check on inputs_baseline_version
    """
    db = await get_db()
    try:
        parent, op = await dal.set_inputs_baseline(
            db=db,
            workspace_id=workspace_id,
            new_inputs=body.model_dump(),
            if_absent_only=if_absent_only,
            expected_version=expected_version,
        )
    except ValueError as e:
        raise HTTPException(status_code=412, detail=str(e))
    except Exception as e:
        logger.exception("set_baseline_inputs_failed", extra=safe_extra({"workspace_id": workspace_id, "err": str(e)}))
        raise HTTPException(status_code=500, detail="Failed to set baseline inputs")

    published = True
    if op == "insert":
        published = publish_event_v1(
            org=_org(), service=Service.ARTIFACT, event="baseline_inputs.set",
            payload={
                "workspace_id": workspace_id,
                "version": parent.inputs_baseline_version,
                "fingerprint": parent.inputs_baseline_fingerprint,
                "op": op,
            },
        )
    elif op == "replace":
        published = publish_event_v1(
            org=_org(), service=Service.ARTIFACT, event="baseline_inputs.replaced",
            payload={
                "workspace_id": workspace_id,
                "version": parent.inputs_baseline_version,
                "fingerprint": parent.inputs_baseline_fingerprint,
                "op": op,
            },
        )

    _set_event_header(response, published)
    response.headers["X-Op"] = op
    response.headers["X-Baseline-Version"] = str(parent.inputs_baseline_version)
    return parent.model_dump()


@router.patch("/{workspace_id}/baseline-inputs")
async def patch_baseline_inputs(
    workspace_id: str,
    body: InputsBaselinePatch,
    response: Response,
    expected_version: Optional[int] = Query(default=None, ge=1),
):
    """
    Merge semantics:
      - Replace AVC or PSS wholesale if present.
      - Upsert into FSS stories by 'key' if fss_stories_upsert provided.
    """
    db = await get_db()
    try:
        updated = await dal.merge_inputs_baseline(
            db=db,
            workspace_id=workspace_id,
            avc=body.avc,
            pss=body.pss,
            fss_stories_upsert=body.fss_stories_upsert,
            expected_version=expected_version,
        )
    except ValueError as e:
        raise HTTPException(status_code=412, detail=str(e))
    except Exception as e:
        logger.exception("patch_baseline_inputs_failed", extra=safe_extra({"workspace_id": workspace_id, "err": str(e)}))
        raise HTTPException(status_code=500, detail="Failed to patch baseline inputs")

    published = publish_event_v1(
        org=_org(), service=Service.ARTIFACT, event="baseline_inputs.merged",
        payload={
            "workspace_id": workspace_id,
            "version": updated.inputs_baseline_version,
            "fingerprint": updated.inputs_baseline_fingerprint,
            "upserts": len(body.fss_stories_upsert or []),
            "replaced_avc": body.avc is not None,
            "replaced_pss": body.pss is not None,
        },
    )
    _set_event_header(response, published)
    response.headers["X-Baseline-Version"] = str(updated.inputs_baseline_version)
    return updated.model_dump()


# ─────────────────────────────────────────────────────────────
# List (filters + pagination over embedded items)
# ─────────────────────────────────────────────────────────────
@router.get("/{workspace_id}")
async def list_artifacts(
    workspace_id: str,
    kind: Optional[str] = Query(default=None, description="Filter by Artifact kind"),
    name_prefix: Optional[str] = Query(default=None, description="Case-insensitive prefix"),
    include_deleted: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    db = await get_db()
    items = await dal.list_artifacts(
        db,
        workspace_id=workspace_id,
        kind=kind,
        name_prefix=name_prefix,
        include_deleted=include_deleted,
        limit=limit,
        offset=offset,
    )
    return items


# ─────────────────────────────────────────────────────────────
# Parent doc (workspace + all artifacts; includes baseline inputs)
# ─────────────────────────────────────────────────────────────
@router.get("/{workspace_id}/parent", response_model=WorkspaceArtifactsDoc)
async def get_workspace_with_artifacts(
    workspace_id: str,
    include_deleted: bool = Query(default=False, description="Include soft-deleted artifacts"),
):
    db = await get_db()
    doc = await dal.get_parent_doc(db, workspace_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Workspace parent not found")

    if include_deleted:
        return doc

    filtered = [a for a in doc.artifacts if a.deleted_at is None]
    return doc.model_copy(update={"artifacts": filtered}, deep=True)


# ─────────────────────────────────────────────────────────────
# Read / HEAD
# ─────────────────────────────────────────────────────────────
@router.get("/{workspace_id}/{artifact_id}")
async def get_artifact(workspace_id: str, artifact_id: str, response: Response):
    db = await get_db()
    art = await dal.get_artifact(db, workspace_id, artifact_id)
    if not art or art.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Not found")
    response.headers["ETag"] = str(art.version)
    return art

@router.head("/{workspace_id}/{artifact_id}")
async def head_artifact(workspace_id: str, artifact_id: str, response: Response):
    db = await get_db()
    art = await dal.get_artifact(db, workspace_id, artifact_id)
    if not art or art.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Not found")
    response.headers["ETag"] = str(art.version)
    return Response(status_code=status.HTTP_200_OK)


# ─────────────────────────────────────────────────────────────
# Replace / Patch / History / Delete
# ─────────────────────────────────────────────────────────────
def _parse_if_match(value: Optional[str]) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        raise HTTPException(status_code=400, detail="If-Match must be an integer version")

def _guard_if_match(expected: Optional[int], actual: int) -> None:
    if expected is not None and expected != actual:
        raise HTTPException(
            status_code=412,
            detail=f"Precondition Failed: expected version {expected}, actual {actual}",
        )

@router.put("/{workspace_id}/{artifact_id}")
async def replace_artifact(
    workspace_id: str,
    artifact_id: str,
    body: ArtifactItemReplace,
    response: Response,
    if_match: Optional[str] = Header(default=None, alias="If-Match"),
):
    db = await get_db()
    art = await dal.get_artifact(db, workspace_id, artifact_id)
    if not art or art.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Not found")

    expected = _parse_if_match(if_match)
    _guard_if_match(expected, art.version)

    updated = await dal.replace_artifact(db, workspace_id, artifact_id, body.data, body.provenance)

    published = publish_event_v1(org=_org(), service=Service.ARTIFACT, event="updated", payload=updated.model_dump())
    if not published:
        logger.error("Event publish failed (replace)", extra=safe_extra({"workspace_id": workspace_id, "artifact_id": artifact_id}))

    response.headers["ETag"] = str(updated.version)
    _set_event_header(response, published)
    return updated

@router.post("/{workspace_id}/{artifact_id}/patch")
async def patch_artifact(
    workspace_id: str,
    artifact_id: str,
    body: ArtifactItemPatchIn,
    response: Response,
    if_match: Optional[str] = Header(default=None, alias="If-Match"),
):
    db = await get_db()
    art = await dal.get_artifact(db, workspace_id, artifact_id)
    if not art or art.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Not found")

    expected = _parse_if_match(if_match)
    _guard_if_match(expected, art.version)

    try:
        new_data = jsonpatch.apply_patch(deepcopy(art.data), body.patch, in_place=False)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid patch: {e}")

    from_version = art.version
    updated = await dal.replace_artifact(db, workspace_id, artifact_id, new_data, body.provenance)
    await dal.record_patch(
        db,
        workspace_id=workspace_id,
        artifact_id=artifact_id,
        from_version=from_version,
        to_version=updated.version,
        patch=body.patch,
        prov=body.provenance,
    )

    published = publish_event_v1(
        org=_org(), service=Service.ARTIFACT, event="patched",
        payload={
            "artifact": updated.model_dump(),
            "from_version": from_version,
            "to_version": updated.version,
            "patch": body.patch
        }
    )
    if not published:
        logger.error("Event publish failed (patch)", extra=safe_extra({"workspace_id": workspace_id, "artifact_id": artifact_id}))

    response.headers["ETag"] = str(updated.version)
    _set_event_header(response, published)
    return updated

@router.get("/{workspace_id}/{artifact_id}/history")
async def history(workspace_id: str, artifact_id: str):
    db = await get_db()
    art = await dal.get_artifact(db, workspace_id, artifact_id)
    if not art:
        raise HTTPException(status_code=404, detail="Not found")
    return await dal.list_patches(db, workspace_id, artifact_id)

@router.delete("/{workspace_id}/{artifact_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_artifact(workspace_id: str, artifact_id: str, response: Response):
    db = await get_db()
    deleted = await dal.soft_delete_artifact(db, workspace_id, artifact_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Not found or already deleted")

    published = publish_event_v1(
        org=_org(), service=Service.ARTIFACT, event="deleted",
        payload={"_id": artifact_id, "workspace_id": workspace_id},
    )
    if not published:
        logger.error("Event publish failed (delete)", extra=safe_extra({"workspace_id": workspace_id, "artifact_id": artifact_id}))

    _set_event_header(response, published)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
