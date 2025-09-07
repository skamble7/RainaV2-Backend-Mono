# services/workspace-service/app/dal/workspace_dal.py
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ReturnDocument

from app.models.workspace import (
    Workspace,
    WorkspaceCreate,
    WorkspaceUpdate,
    AccessLevel,
    PlatformSection,
)

COL = "workspaces"

__all__ = [
    "create_workspace",
    "get_workspace",
    "list_workspaces",
    "update_workspace",
    "merge_platform_config",
    "delete_workspace",
]


# ----------------- CRUD -----------------

async def create_workspace(db: AsyncIOMotorDatabase, data: WorkspaceCreate) -> Workspace:
    now = datetime.now(timezone.utc)

    origin_platform = (data.origin_platform or "raina").lower()
    visibility = data.visibility or {origin_platform: AccessLevel.owner}

    # Normalize visibility enum -> string for storage
    vis_doc = {k: (v.value if hasattr(v, "value") else str(v)) for k, v in visibility.items()}

    # Optional platform_config seed
    pc_doc: Dict[str, Any] = {}
    if data.platform_config:
        for k, section in data.platform_config.items():
            pc_doc[k.lower()] = _section_to_doc(section)

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
        "platform_config": pc_doc,
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
    upd: Dict[str, Any] = {k: v for k, v in patch.model_dump(exclude_unset=True).items()}

    # Normalize visibility enum -> string for storage
    if "visibility" in upd and upd["visibility"] is not None:
        upd["visibility"] = {k: (v.value if hasattr(v, "value") else str(v)) for k, v in upd["visibility"].items()}

    # Full replace of platform_config (if provided)
    if "platform_config" in upd and upd["platform_config"] is not None:
        repl: Dict[str, Any] = {}
        for k, section in upd["platform_config"].items():
            repl[k.lower()] = _section_to_doc(section)
        upd["platform_config"] = repl

    if not upd:
        doc = await db[COL].find_one({"_id": wid})
        return _to_model(doc) if doc else None

    upd["updated_at"] = datetime.now(timezone.utc)
    res = await db[COL].find_one_and_update(
        {"_id": wid},
        {"$set": upd},
        return_document=ReturnDocument.AFTER,
    )
    return _to_model(res) if res else None


async def merge_platform_config(
    db: AsyncIOMotorDatabase, wid: str, platform: str, patch: Dict[str, Any]
) -> Optional[Workspace]:
    """
    Merge (upsert) keys for a single platform section without replacing others.
    """
    platform = platform.lower()
    now = datetime.now(timezone.utc)
    set_ops = {f"platform_config.{platform}.{k}": v for k, v in patch.items()}
    set_ops["updated_at"] = now
    res = await db[COL].find_one_and_update(
        {"_id": wid},
        {"$set": set_ops},
        return_document=ReturnDocument.AFTER,
    )
    return _to_model(res) if res else None


async def delete_workspace(db: AsyncIOMotorDatabase, wid: str) -> bool:
    res = await db[COL].delete_one({"_id": wid})
    return res.deleted_count == 1


# ----------------- Helpers -----------------

def _section_to_doc(section: PlatformSection | Dict[str, Any]) -> Dict[str, Any]:
    if isinstance(section, PlatformSection):
        return section.model_dump(exclude_none=True)
    # already a dict (from raw payload)
    return {k: v for k, v in section.items() if v is not None}


def _to_model(doc) -> Workspace:
    if not doc:
        return None  # type: ignore

    origin_platform = doc.get("origin_platform") or None
    visibility = doc.get("visibility") or {}
    pc = doc.get("platform_config") or {}

    # Convert platform_config dict -> PlatformSection objects
    pc_model = {
        k: PlatformSection(**v) if isinstance(v, dict) else PlatformSection()
        for k, v in pc.items()
    }

    return Workspace(
        id=str(doc["_id"]),
        name=doc["name"],
        description=doc.get("description"),
        created_by=doc.get("created_by"),
        created_at=doc["created_at"],
        updated_at=doc["updated_at"],
        origin_platform=origin_platform,
        visibility=visibility,
        platform_config=pc_model,
    )
