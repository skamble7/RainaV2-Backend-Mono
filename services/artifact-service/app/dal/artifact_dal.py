from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ASCENDING, DESCENDING

from ..models.artifact import (
    ArtifactItem,
    ArtifactItemCreate,
    ArtifactItemReplace,
    ArtifactItemPatchIn,
    WorkspaceArtifactsDoc,
    WorkspaceSnapshot,
    Provenance,
)

WORKSPACE_ARTIFACTS = "workspace_artifacts"  # ← define here; no self-import

PATCHES = "artifact_patches"


# -----------------------------
# Indexes
# -----------------------------
async def ensure_indexes(db: AsyncIOMotorDatabase):
    # One doc per workspace
    await db[WORKSPACE_ARTIFACTS].create_index([("workspace_id", ASCENDING)], unique=True)

    # Speed lookups by embedded artifact_id and kind/name filtering
    await db[WORKSPACE_ARTIFACTS].create_index([("artifacts.artifact_id", ASCENDING)])
    await db[WORKSPACE_ARTIFACTS].create_index(
        [("workspace_id", ASCENDING), ("artifacts.kind", ASCENDING), ("artifacts.name", ASCENDING)]
    )
    await db[WORKSPACE_ARTIFACTS].create_index([("artifacts.deleted_at", ASCENDING)])

    # Patch history (unchanged)
    await db[PATCHES].create_index([("artifact_id", ASCENDING), ("workspace_id", ASCENDING), ("to_version", DESCENDING)])


# -----------------------------
# Parent doc lifecycle
# -----------------------------
async def create_parent_doc(
    db: AsyncIOMotorDatabase, workspace: WorkspaceSnapshot
) -> WorkspaceArtifactsDoc:
    now = datetime.utcnow()
    doc = {
        "_id": str(uuid.uuid4()),
        "workspace_id": workspace.id,  # workspace._id alias accepted by model
        "workspace": workspace.model_dump(by_alias=True),
        "artifacts": [],
        "created_at": now,
        "updated_at": now,
    }
    await db[WORKSPACE_ARTIFACTS].insert_one(doc)
    return WorkspaceArtifactsDoc(**doc)


async def get_parent_doc(db: AsyncIOMotorDatabase, workspace_id: str) -> Optional[WorkspaceArtifactsDoc]:
    d = await db[WORKSPACE_ARTIFACTS].find_one({"workspace_id": workspace_id})
    return WorkspaceArtifactsDoc(**d) if d else None


# -----------------------------
# CRUD on embedded artifacts
# -----------------------------
async def add_artifact(
    db: AsyncIOMotorDatabase,
    workspace_id: str,
    payload: ArtifactItemCreate,
    prov: Optional[Provenance],
) -> ArtifactItem:
    now = datetime.utcnow()
    item = ArtifactItem(
        artifact_id=str(uuid.uuid4()),
        kind=payload.kind,
        name=payload.name,
        data=payload.data,
        version=1,
        created_at=now,
        updated_at=now,
        provenance=prov,
    )
    res = await db[WORKSPACE_ARTIFACTS].update_one(
        {"workspace_id": workspace_id},
        {"$push": {"artifacts": item.model_dump()},
         "$set": {"updated_at": now}},
    )
    if res.matched_count == 0:
        raise ValueError(f"Workspace parent not found for {workspace_id}")
    return item


async def list_artifacts(
    db: AsyncIOMotorDatabase,
    workspace_id: str,
    kind: Optional[str] = None,
    name_prefix: Optional[str] = None,
    include_deleted: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    """
    Returns flattened list of embedded artifacts for a workspace, honoring filters & pagination.
    """
    match_stage = {"$match": {"workspace_id": workspace_id}}
    pipeline = [
        match_stage,
        {"$unwind": "$artifacts"},
    ]

    conds = []
    if not include_deleted:
        conds.append({"artifacts.deleted_at": None})
    if kind:
        conds.append({"artifacts.kind": kind})
    if name_prefix:
        conds.append({"artifacts.name": {"$regex": f"^{name_prefix}", "$options": "i"}})
    if conds:
        pipeline.append({"$match": {"$and": conds}})

    pipeline += [
        {"$sort": {"artifacts.updated_at": -1, "artifacts.artifact_id": 1}},
        {"$skip": max(offset, 0)},
        {"$limit": min(limit, 200)},
        {"$replaceRoot": {"newRoot": "$artifacts"}},
    ]

    cur = db[WORKSPACE_ARTIFACTS].aggregate(pipeline)
    return [d async for d in cur]


async def get_artifact(
    db: AsyncIOMotorDatabase, workspace_id: str, artifact_id: str
) -> Optional[ArtifactItem]:
    pipeline = [
        {"$match": {"workspace_id": workspace_id}},
        {"$unwind": "$artifacts"},
        {"$match": {"artifacts.artifact_id": artifact_id}},
        {"$replaceRoot": {"newRoot": "$artifacts"}},
    ]
    cur = db[WORKSPACE_ARTIFACTS].aggregate(pipeline)
    doc = await cur.to_list(length=1)
    return ArtifactItem(**doc[0]) if doc else None


async def get_artifact_by_name(
    db: AsyncIOMotorDatabase, workspace_id: str, kind: str, name: str
) -> Optional[ArtifactItem]:
    pipeline = [
        {"$match": {"workspace_id": workspace_id}},
        {"$unwind": "$artifacts"},
        {"$match": {"artifacts.kind": kind, "artifacts.name": name}},
        {"$replaceRoot": {"newRoot": "$artifacts"}},
    ]
    cur = db[WORKSPACE_ARTIFACTS].aggregate(pipeline)
    doc = await cur.to_list(length=1)
    return ArtifactItem(**doc[0]) if doc else None


async def replace_artifact(
    db: AsyncIOMotorDatabase,
    workspace_id: str,
    artifact_id: str,
    new_data: Dict[str, Any],
    prov: Optional[Provenance],
) -> ArtifactItem:
    """
    Replaces the 'data' of the embedded artifact, increments version, updates provenance.
    """
    now = datetime.utcnow()
    res = await db[WORKSPACE_ARTIFACTS].find_one_and_update(
        {"workspace_id": workspace_id},
        {
            "$set": {
                "artifacts.$[a].data": new_data,
                "artifacts.$[a].updated_at": now,
                "artifacts.$[a].provenance": (prov.model_dump() if prov else None),
                "updated_at": now,
            },
            "$inc": {"artifacts.$[a].version": 1},
        },
        array_filters=[{"a.artifact_id": artifact_id}],
        return_document=True,
        projection={"artifacts": 1, "_id": 0},
    )
    if not res:
        raise ValueError("Artifact or workspace not found")

    # pick the updated artifact from array
    for a in res["artifacts"]:
        if a.get("artifact_id") == artifact_id:
            return ArtifactItem(**a)
    raise ValueError("Updated artifact not found after replace")


async def soft_delete_artifact(
    db: AsyncIOMotorDatabase, workspace_id: str, artifact_id: str
) -> Optional[ArtifactItem]:
    now = datetime.utcnow()
    res = await db[WORKSPACE_ARTIFACTS].find_one_and_update(
        {"workspace_id": workspace_id},
        {
            "$set": {
                "artifacts.$[a].deleted_at": now,
                "artifacts.$[a].updated_at": now,
                "updated_at": now,
            }
        },
        array_filters=[{"a.artifact_id": artifact_id, "a.deleted_at": None}],
        return_document=True,
        projection={"artifacts": 1, "_id": 0},
    )
    if not res:
        return None
    for a in res["artifacts"]:
        if a.get("artifact_id") == artifact_id:
            return ArtifactItem(**a)
    return None


# -----------------------------
# Patch history (unchanged)
# -----------------------------
async def record_patch(
    db: AsyncIOMotorDatabase,
    workspace_id: str,
    artifact_id: str,
    from_version: int,
    to_version: int,
    patch: List[Dict[str, Any]],
    prov: Optional[Provenance],
):
    doc = {
        "_id": str(uuid.uuid4()),
        "artifact_id": artifact_id,
        "workspace_id": workspace_id,
        "from_version": from_version,
        "to_version": to_version,
        "patch": patch,
        "created_at": datetime.utcnow(),
        "provenance": prov.model_dump() if prov else None,
    }
    await db[PATCHES].insert_one(doc)


async def list_patches(
    db: AsyncIOMotorDatabase, workspace_id: str, artifact_id: str
) -> List[Dict[str, Any]]:
    cur = db[PATCHES].find({"workspace_id": workspace_id, "artifact_id": artifact_id}).sort("to_version", 1)
    return [d async for d in cur]

async def refresh_workspace_snapshot(db, workspace: "WorkspaceSnapshot") -> bool:
    """
    Update the denormalized workspace snapshot inside the parent doc.
    If parent doesn't exist yet (rare race), create it.
    Returns True when an update/insert was applied.
    """
    now = datetime.utcnow()
    res = await db[WORKSPACE_ARTIFACTS].update_one(
        {"workspace_id": workspace.id},
        {
            "$set": {
                "workspace": workspace.model_dump(by_alias=True),
                "updated_at": now,
            }
        },
    )
    if res.matched_count == 0:
        # Parent missing? create it to be safe.
        await create_parent_doc(db, workspace)
        return True
    return True


async def delete_parent_doc(db, workspace_id: str) -> bool:
    """
    Hard-delete the parent doc for a workspace.
    (If you prefer soft delete, we can switch to setting deleted_at on parent + artifacts.)
    """
    res = await db[WORKSPACE_ARTIFACTS].delete_one({"workspace_id": workspace_id})
    return res.deleted_count == 1
