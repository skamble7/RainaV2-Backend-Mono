# app/dal/guidance_doc_dal.py
from __future__ import annotations
from datetime import datetime
from typing import Optional, List, Dict, Any

from app.config import settings
from app.db.mongodb import get_collection

COLL = settings.GUIDANCE_COLLECTION

async def ensure_indexes():
    coll = get_collection(COLL)
    # workspace_id + version unique to guarantee proper bumping
    await coll.create_index([("workspace_id", 1), ("version", -1)], unique=True, name="ws_ver_unique")
    await coll.create_index([("workspace_id", 1), ("created_at", -1)], name="ws_created_idx")

async def next_version_for(workspace_id: str) -> int:
    coll = get_collection(COLL)
    doc = await coll.find_one({"workspace_id": workspace_id}, sort=[("version", -1)])
    if not doc:
        return 1
    return int(doc.get("version", 0)) + 1

async def insert_record(
    *,
    workspace_id: str,
    workspace_name: str,
    filename_md: str,
    filename_pdf: Optional[str],
    version: int,
    sections: List[str],
    meta: Dict[str, Any],
) -> str:
    coll = get_collection(COLL)
    now = datetime.utcnow()
    res = await coll.insert_one({
        "workspace_id": workspace_id,
        "workspace_name": workspace_name,
        "filename_md": filename_md,
        "filename_pdf": filename_pdf,
        "version": version,
        "sections": sections,
        "meta": meta or {},
        "created_at": now,
    })
    return str(res.inserted_id)

async def list_by_workspace(workspace_id: str) -> List[Dict[str, Any]]:
    coll = get_collection(COLL)
    cur = coll.find({"workspace_id": workspace_id}).sort([("version", -1)])
    return [doc async for doc in cur]

async def get_by_workspace_and_filename(workspace_id: str, filename: str) -> Optional[Dict[str, Any]]:
    coll = get_collection(COLL)
    return await coll.find_one({
        "workspace_id": workspace_id,
        "$or": [{"filename_md": filename}, {"filename_pdf": filename}],
    })

async def delete_by_workspace_and_filename(workspace_id: str, filename: str) -> int:
    coll = get_collection(COLL)
    res = await coll.delete_one({
        "workspace_id": workspace_id,
        "$or": [{"filename_md": filename}, {"filename_pdf": filename}],
    })
    return res.deleted_count
