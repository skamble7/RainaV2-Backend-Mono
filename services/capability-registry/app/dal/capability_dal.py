import uuid
from datetime import datetime
from typing import Optional, List
from motor.motor_asyncio import AsyncIOMotorDatabase
from ..models.capability_pack import CapabilityPack, CapabilityPackCreate, CapabilityPackUpdate

COL = "capability_packs"

async def ensure_indexes(db: AsyncIOMotorDatabase):
    await db[COL].create_index([("key", 1), ("version", 1)], unique=True)
    await db[COL].create_index([("title", "text"), ("description", "text")])

async def create_pack(db: AsyncIOMotorDatabase, body: CapabilityPackCreate) -> CapabilityPack:
    now = datetime.utcnow()
    doc = {
        "_id": str(uuid.uuid4()),
        "key": body.key,
        "version": body.version,
        "title": body.title,
        "description": body.description,
        "capabilities": [c.model_dump() for c in body.capabilities],
        "playbooks": [p.model_dump() for p in body.playbooks],
        "created_at": now,
        "updated_at": now,
    }
    await db[COL].insert_one(doc)
    return CapabilityPack(**doc)

async def get_pack(db: AsyncIOMotorDatabase, key: str, version: str) -> Optional[CapabilityPack]:
    d = await db[COL].find_one({"key": key, "version": version})
    return CapabilityPack(**d) if d else None

async def list_packs(db: AsyncIOMotorDatabase, key: Optional[str], q: Optional[str], limit: int, offset: int) -> List[dict]:
    query = {}
    if key: query["key"] = key
    if q: query["$text"] = {"$search": q}
    cur = db[COL].find(query).sort([("updated_at", -1)]).skip(offset).limit(min(limit, 200))
    return [d async for d in cur]

async def upsert_pack(db: AsyncIOMotorDatabase, key: str, version: str, patch: CapabilityPackUpdate) -> CapabilityPack:
    now = datetime.utcnow()
    update = {k: v for k, v in patch.model_dump(exclude_none=True).items()}
    update["updated_at"] = now
    d = await db[COL].find_one_and_update(
        {"key": key, "version": version},
        {"$set": update},
        upsert=False,
        return_document=True,
    )
    return CapabilityPack(**d) if d else None

async def delete_pack(db: AsyncIOMotorDatabase, key: str, version: str) -> bool:
    res = await db[COL].delete_one({"key": key, "version": version})
    return res.deleted_count == 1
