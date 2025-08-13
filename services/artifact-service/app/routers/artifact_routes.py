# services/artifact-service/app/routers/artifact_routes.py
from __future__ import annotations

from copy import deepcopy
import logging
from typing import Optional

import jsonpatch
from fastapi import APIRouter, HTTPException, Header, Query, Response, status
from fastapi.responses import ORJSONResponse
from pymongo.errors import DuplicateKeyError  # motor/pymongo duplicate key

from ..config import settings
from ..db.mongodb import get_db
from ..events.rabbit import publish_event_v1
from ..dal import artifact_dal as dal
from ..models.artifact import (
    ArtifactItemCreate,
    ArtifactItemReplace,
    ArtifactItemPatchIn,
    WorkspaceArtifactsDoc,
)
from libs.raina_common.events import Service  # versioned routing (service segment)

# --- Reserved key protection for logger.extra (quick fix) ---------------
_RESERVED = {
    "name", "msg", "args", "levelname", "levelno", "pathname", "filename", "module",
    "exc_info", "exc_text", "stack_info", "lineno", "funcName", "created", "msecs",
    "relativeCreated", "thread", "threadName", "process", "processName", "message", "asctime"
}

def safe_extra(extra: dict) -> dict:
    out = {}
    for k, v in extra.items():
        if k in _RESERVED:
            out[f"ctx_{k}"] = v  # rename to avoid LogRecord collisions
        else:
            out[k] = v
    return out

logger = logging.getLogger("app.routes.artifact")

router = APIRouter(
    prefix="/artifact",
    tags=["artifact"],
    default_response_class=ORJSONResponse,
)

# ─────────────────────────────────────────────────────────────
# Helpers
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


def _set_event_header(response: Response, published: bool) -> None:
    # Non-breaking way to expose publish outcome
    response.headers["X-Event-Published"] = "true" if published else "false"


# Convenience: org segment for routing keys
def _org() -> str:
    return settings.events_org  # default "raina"


# ─────────────────────────────────────────────────────────────
# Create embedded artifact under a workspace parent
# ─────────────────────────────────────────────────────────────
@router.post("/{workspace_id}", status_code=status.HTTP_201_CREATED)
async def create_artifact(
    workspace_id: str,
    body: ArtifactItemCreate,
    response: Response,
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
):
    """
    Idempotent create:
    - If artifact (kind+name) already exists, return 200 with the existing item (no 409).
    - On race DuplicateKeyError, fetch and return the existing item with 200.
    - Publishes 'raina.artifact.created.v1' only on the first successful insert.
    """
    db = await get_db()

    # Fast path: if already exists, return it (idempotent)
    existing = await dal.get_artifact_by_name(db, workspace_id, body.kind, body.name)
    if existing:
        logger.info(
            "Artifact create idempotent replay (precheck hit)",
            extra=safe_extra({
                "workspace_id": workspace_id,
                "kind": body.kind,
                "artifact_name": body.name,
                "idempotency_key": idempotency_key,
            }),
        )
        response.headers["ETag"] = str(existing.version)
        response.headers["X-Idempotent-Replay"] = "true"
        return ORJSONResponse(existing.model_dump(), status_code=status.HTTP_200_OK)

    # Try to insert
    try:
        art = await dal.add_artifact(db, workspace_id, body, body.provenance)
        created = True
    except DuplicateKeyError:
        # Another request won the race; fetch and return it
        logger.info(
            "Artifact create idempotent replay (race)",
            extra=safe_extra({
                "workspace_id": workspace_id,
                "kind": body.kind,
                "artifact_name": body.name,
                "idempotency_key": idempotency_key,
            }),
        )
        art = await dal.get_artifact_by_name(db, workspace_id, body.kind, body.name)
        if not art:
            # extremely rare: index not visible yet; fall back to 409 to avoid lying
            raise HTTPException(status_code=409, detail="Artifact with same kind+name exists")
        created = False

    # Only publish 'created' when we truly created it
    published = True
    if created:
        published = publish_event_v1(
            org=_org(),
            service=Service.ARTIFACT,
            event="created",
            payload=art.model_dump(),
        )
        if not published:
            logger.error(
                "Event publish failed (create not blocked)",
                extra=safe_extra({
                    "workspace_id": workspace_id,
                    "artifact_id": art.id,
                }),
            )

    response.headers["ETag"] = str(art.version)
    _set_event_header(response, published)
    if created:
        return ORJSONResponse(art.model_dump(), status_code=status.HTTP_201_CREATED)
    else:
        response.headers["X-Idempotent-Replay"] = "true"
        return ORJSONResponse(art.model_dump(), status_code=status.HTTP_200_OK)


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
# Parent doc (workspace + all artifacts)
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
# Read (sets ETag)
# ─────────────────────────────────────────────────────────────
@router.get("/{workspace_id}/{artifact_id}")
async def get_artifact(workspace_id: str, artifact_id: str, response: Response):
    db = await get_db()
    art = await dal.get_artifact(db, workspace_id, artifact_id)
    if not art or art.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Not found")
    response.headers["ETag"] = str(art.version)
    return art


# ─────────────────────────────────────────────────────────────
# HEAD – lightweight change check via ETag only
# ─────────────────────────────────────────────────────────────
@router.head("/{workspace_id}/{artifact_id}")
async def head_artifact(workspace_id: str, artifact_id: str, response: Response):
    db = await get_db()
    art = await dal.get_artifact(db, workspace_id, artifact_id)
    if not art or art.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Not found")
    response.headers["ETag"] = str(art.version)
    return Response(status_code=status.HTTP_200_OK)


# ─────────────────────────────────────────────────────────────
# Replace (optimistic concurrency via If-Match)
# ─────────────────────────────────────────────────────────────
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

    published = publish_event_v1(
        org=_org(),
        service=Service.ARTIFACT,
        event="updated",
        payload=updated.model_dump(),
    )
    if not published:
        logger.error(
            "Event publish failed (replace not blocked)",
            extra=safe_extra({
                "workspace_id": workspace_id,
                "artifact_id": artifact_id,
                "to_version": updated.version,
            }),
        )

    response.headers["ETag"] = str(updated.version)
    _set_event_header(response, published)
    return updated


# ─────────────────────────────────────────────────────────────
# Patch (optimistic concurrency via If-Match)
# ─────────────────────────────────────────────────────────────
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

    # record patch history
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
        org=_org(),
        service=Service.ARTIFACT,
        event="patched",
        payload={
            "artifact": updated.model_dump(),
            "from_version": from_version,
            "to_version": updated.version,
            "patch": body.patch,
        },
    )
    if not published:
        logger.error(
            "Event publish failed (patch not blocked)",
            extra=safe_extra({
                "workspace_id": workspace_id,
                "artifact_id": artifact_id,
                "from_version": from_version,
                "to_version": updated.version,
            }),
        )

    response.headers["ETag"] = str(updated.version)
    _set_event_header(response, published)
    return updated


# ─────────────────────────────────────────────────────────────
# History
# ─────────────────────────────────────────────────────────────
@router.get("/{workspace_id}/{artifact_id}/history")
async def history(workspace_id: str, artifact_id: str):
    db = await get_db()
    art = await dal.get_artifact(db, workspace_id, artifact_id)
    if not art:
        raise HTTPException(status_code=404, detail="Not found")
    return await dal.list_patches(db, workspace_id, artifact_id)


# ─────────────────────────────────────────────────────────────
# Soft delete
# ─────────────────────────────────────────────────────────────
@router.delete("/{workspace_id}/{artifact_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_artifact(workspace_id: str, artifact_id: str, response: Response):
    db = await get_db()
    deleted = await dal.soft_delete_artifact(db, workspace_id, artifact_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Not found or already deleted")

    published = publish_event_v1(
        org=_org(),
        service=Service.ARTIFACT,
        event="deleted",
        payload={"_id": artifact_id, "workspace_id": workspace_id},
    )
    if not published:
        logger.error(
            "Event publish failed (delete not blocked)",
            extra=safe_extra({
                "workspace_id": workspace_id,
                "artifact_id": artifact_id,
            }),
        )

    _set_event_header(response, published)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
