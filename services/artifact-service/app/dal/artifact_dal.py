import uuid
from datetime import datetime
from typing import Optional
from motor.motor_asyncio import AsyncIOMotorDatabase
from ..models.artifact import Artifact, Provenance

ARTIFACTS = "artifacts"
PATCHES = "artifact_patches"

async def ensure_indexes(db):
    await db[ARTIFACTS].create_index([("workspace_id", 1), ("_id", 1)], unique=True)
    await db[ARTIFACTS].create_index([("workspace_id", 1), ("kind", 1), ("name", 1)], unique=True)
    await db[ARTIFACTS].create_index([("workspace_id", 1), ("deleted_at", 1)])
    await db[PATCHES].create_index([("artifact_id", 1), ("workspace_id", 1), ("to_version", -1)])

async def list_artifacts(
    db, workspace_id: str,
    kind: Optional[str] = None,
    name_prefix: Optional[str] = None,
    include_deleted: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    q = {"workspace_id": workspace_id}
    if not include_deleted:
        q["deleted_at"] = None
    if kind:
        q["kind"] = kind
    if name_prefix:
        q["name"] = {"$regex": f"^{name_prefix}", "$options": "i"}
    cur = (
        db[ARTIFACTS]
        .find(q)
        .sort([("updated_at", -1), ("_id", 1)])
        .skip(offset)
        .limit(min(limit, 200))
    )
    return [d async for d in cur]

async def soft_delete_artifact(db, workspace_id: str, artifact_id: str) -> Optional[Artifact]:
    now = datetime.utcnow()
    res = await db[ARTIFACTS].find_one_and_update(
        {"workspace_id": workspace_id, "_id": artifact_id, "deleted_at": None},
        {"$set": {"deleted_at": now, "updated_at": now}},
        return_document=True,
    )
    return Artifact(**res) if res else None

async def create_artifact(db: AsyncIOMotorDatabase, workspace_id: str, kind: str, name: str, data: dict, prov: Optional[Provenance]) -> Artifact:
    now = datetime.utcnow()
    doc = {
        "_id": str(uuid.uuid4()),
        "workspace_id": workspace_id,
        "kind": kind,
        "name": name,
        "data": data,
        "version": 1,
        "created_at": now,
        "updated_at": now,
        "provenance": prov.model_dump() if prov else None,
    }
    await db[ARTIFACTS].insert_one(doc)
    return Artifact(**doc)

async def get_artifact(db: AsyncIOMotorDatabase, workspace_id: str, artifact_id: str) -> Optional[Artifact]:
    doc = await db[ARTIFACTS].find_one({"workspace_id": workspace_id, "_id": artifact_id})
    return Artifact(**doc) if doc else None

async def get_artifact_by_name(db: AsyncIOMotorDatabase, workspace_id: str, kind: str, name: str) -> Optional[Artifact]:
    doc = await db[ARTIFACTS].find_one({"workspace_id": workspace_id, "kind": kind, "name": name})
    return Artifact(**doc) if doc else None

async def replace_artifact(db: AsyncIOMotorDatabase, a: Artifact, new_data: dict, prov: Optional[Provenance]) -> Artifact:
    new_version = a.version + 1
    now = datetime.utcnow()
    await db[ARTIFACTS].update_one(
        {"_id": a.id, "workspace_id": a.workspace_id},
        {"$set": {
            "data": new_data, "version": new_version, "updated_at": now,
            "provenance": (prov.model_dump() if prov else a.provenance)
        }}
    )
    updated = await db[ARTIFACTS].find_one({"_id": a.id})
    return Artifact(**updated)

async def record_patch(db: AsyncIOMotorDatabase, a: Artifact, from_version: int, to_version: int, patch: list[dict], prov: Optional[Provenance]):
    doc = {
        "_id": str(uuid.uuid4()),
        "artifact_id": a.id,
        "workspace_id": a.workspace_id,
        "from_version": from_version,
        "to_version": to_version,
        "patch": patch,
        "created_at": datetime.utcnow(),
        "provenance": prov.model_dump() if prov else None,
    }
    await db[PATCHES].insert_one(doc)

async def list_patches(db: AsyncIOMotorDatabase, workspace_id: str, artifact_id: str) -> list[dict]:
    cur = db[PATCHES].find({"workspace_id": workspace_id, "artifact_id": artifact_id}).sort("to_version", 1)
    return [d async for d in cur]
