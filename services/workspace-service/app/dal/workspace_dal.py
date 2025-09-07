# services/workspace-service/app/dal/workspace_dal.py
import uuid
from datetime import datetime, timezone
from typing import Optional
from motor.motor_asyncio import AsyncIOMotorDatabase
from app.models.workspace import Workspace, WorkspaceCreate, WorkspaceUpdate, AccessLevel

COL = "workspaces"


async def create_workspace(db: AsyncIOMotorDatabase, data: WorkspaceCreate) -> Workspace:
    now = datetime.now(timezone.utc)

    # Defaults are expected to be injected by the router, but we also guard here for safety.
    origin_platform = (data.origin_platform or "raina").lower()
    visibility = data.visibility or {origin_platform: AccessLevel.owner}

    # Normalize visibility enum values to string for storage (Mongo-friendly)
    vis_doc = {k: (v.value if hasattr(v, "value") else str(v)) for k, v in visibility.items()}

    doc = {
        "_id": str(uuid.uuid4()),
        "name": data.name,
        "description": data.description,
        "created_by": data.created_by,
        "created_at": now,
        "updated_at": now,
        # new
        "origin_platform": origin_platform,
        "visibility": vis_doc,
    }
    await db[COL].insert_one(doc)
    return _to_model(doc)


async def get_workspace(db: AsyncIOMotorDatabase, wid: str) -> Optional[Workspace]:
    doc = await db[COL].find_one({"_id": wid})
    return _to_model(doc) if doc else None


async def list_workspaces(db: AsyncIOMotorDatabase, q: str | None = None) -> list[Workspace]:
    query = {"name": {"$regex": q, "$options": "i"}} if q else {}
    cur = db[COL].find(query).sort("created_at", 1)
    return [_to_model(d) async for d in cur]


async def update_workspace(db: AsyncIOMotorDatabase, wid: str, patch: WorkspaceUpdate) -> Optional[Workspace]:
    upd = {k: v for k, v in patch.model_dump(exclude_unset=True).items()}

    # If visibility provided, normalize enum → string for storage
    if "visibility" in upd and upd["visibility"] is not None:
        upd["visibility"] = {k: (v.value if hasattr(v, "value") else str(v)) for k, v in upd["visibility"].items()}

    if not upd:
        doc = await db[COL].find_one({"_id": wid})
        return _to_model(doc) if doc else None

    upd["updated_at"] = datetime.now(timezone.utc)
    res = await db[COL].find_one_and_update(
        {"_id": wid}, {"$set": upd}, return_document=True
    )
    return _to_model(res) if res else None


async def delete_workspace(db: AsyncIOMotorDatabase, wid: str) -> bool:
    res = await db[COL].delete_one({"_id": wid})
    return res.deleted_count == 1


# helpers

def _to_model(doc) -> Workspace:
    # Backward compatibility for old docs (no origin/visibility)
    origin_platform = (doc.get("origin_platform") or None)
    visibility = doc.get("visibility") or {}
    return Workspace(
        id=str(doc["_id"]),
        name=doc["name"],
        description=doc.get("description"),
        created_by=doc.get("created_by"),
        created_at=doc["created_at"],
        updated_at=doc["updated_at"],
        origin_platform=origin_platform,
        visibility=visibility,
    )
