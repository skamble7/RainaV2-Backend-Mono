import uuid
from datetime import datetime, timezone
from typing import Optional
from motor.motor_asyncio import AsyncIOMotorDatabase
from app.models.workspace import Workspace, WorkspaceCreate, WorkspaceUpdate

COL = "workspaces"

async def create_workspace(db: AsyncIOMotorDatabase, data: WorkspaceCreate) -> Workspace:
    now = datetime.now(timezone.utc)
    doc = {
        "_id": str(uuid.uuid4()),
        "name": data.name,
        "description": data.description,
        "created_by": data.created_by,
        "created_at": now,
        "updated_at": now,
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
    return Workspace(
        id=str(doc["_id"]),
        name=doc["name"],
        description=doc.get("description"),
        created_by=doc.get("created_by"),
        created_at=doc["created_at"],
        updated_at=doc["updated_at"],
    )   