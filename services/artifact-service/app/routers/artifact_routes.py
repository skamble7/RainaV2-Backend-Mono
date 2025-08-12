# app/routers/artifact_routes.py
from copy import deepcopy
import jsonpatch
from fastapi import APIRouter, HTTPException, Header, Query, Response
from fastapi.responses import ORJSONResponse

from ..db.mongodb import get_db
from ..events.rabbit import publish_event
from ..dal import artifact_dal as dal
from ..models.artifact import ArtifactItemCreate, ArtifactItemReplace, ArtifactItemPatchIn

router = APIRouter(prefix="/artifact", tags=["artifact"], default_response_class=ORJSONResponse)


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────
def _parse_if_match(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        raise HTTPException(status_code=400, detail="If-Match must be an integer version")


def _guard_if_match(expected: int | None, actual: int) -> None:
    if expected is not None and expected != actual:
        raise HTTPException(
            status_code=412,
            detail=f"Precondition Failed: expected version {expected}, actual {actual}",
        )


# ─────────────────────────────────────────────────────────────
# Create embedded artifact under a workspace parent
# ─────────────────────────────────────────────────────────────
@router.post("/{workspace_id}", status_code=201)
async def create_artifact(workspace_id: str, body: ArtifactItemCreate, response: Response):
    db = await get_db()
    if await dal.get_artifact_by_name(db, workspace_id, body.kind, body.name):
        raise HTTPException(status_code=409, detail="Artifact with same kind+name exists")

    art = await dal.add_artifact(db, workspace_id, body, body.provenance)
    try:
        publish_event("artifact.created", art.model_dump())
    except Exception:
        pass
    response.headers["ETag"] = str(art.version)
    return art


# ─────────────────────────────────────────────────────────────
# List (filters + pagination over embedded items)
# ─────────────────────────────────────────────────────────────
@router.get("/{workspace_id}")
async def list_artifacts(
    workspace_id: str,
    kind: str | None = Query(default=None, description="Filter by Artifact kind"),
    name_prefix: str | None = Query(default=None, description="Case-insensitive prefix"),
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
from ..models.artifact import WorkspaceArtifactsDoc  # add near your other imports

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

    # return a copy with only active artifacts
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
    return Response(status_code=200)


# ─────────────────────────────────────────────────────────────
# Replace (optimistic concurrency via If-Match)
# ─────────────────────────────────────────────────────────────
@router.put("/{workspace_id}/{artifact_id}")
async def replace_artifact(
    workspace_id: str,
    artifact_id: str,
    body: ArtifactItemReplace,
    response: Response,
    if_match: str | None = Header(default=None, alias="If-Match"),
):
    db = await get_db()
    art = await dal.get_artifact(db, workspace_id, artifact_id)
    if not art or art.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Not found")

    expected = _parse_if_match(if_match)
    _guard_if_match(expected, art.version)

    updated = await dal.replace_artifact(db, workspace_id, artifact_id, body.data, body.provenance)
    publish_event("artifact.updated", updated.model_dump())
    response.headers["ETag"] = str(updated.version)
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
    if_match: str | None = Header(default=None, alias="If-Match"),
):
    db = await get_db()
    art = await     dal.get_artifact(db, workspace_id, artifact_id)
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

    publish_event(
        "artifact.patched",
        {
            "artifact": updated.model_dump(),
            "from_version": from_version,
            "to_version": updated.version,
            "patch": body.patch,
        },
    )
    response.headers["ETag"] = str(updated.version)
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
@router.delete("/{workspace_id}/{artifact_id}", status_code=204)
async def delete_artifact(workspace_id: str, artifact_id: str):
    db = await get_db()
    deleted = await dal.soft_delete_artifact(db, workspace_id, artifact_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Not found or already deleted")
    publish_event("artifact.deleted", {"_id": artifact_id, "workspace_id": workspace_id})
    return Response(status_code=204)
