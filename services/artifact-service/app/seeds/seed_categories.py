# services/artifact-service/app/seeds/seed_categories.py
from __future__ import annotations

from typing import Dict, List
from datetime import datetime

from app.db.mongodb import get_db
from app.dal.category_dal import ensure_indexes
from motor.motor_asyncio import AsyncIOMotorDatabase

# All category keys (second segment of KIND) pulled from your taxonomy
CATEGORY_KEYS: List[str] = [
    "diagram","pat","dam","contract","model","catalog","workflow","security","data",
    "infra","obs","gov","risk","ops","finops","qa","perf","asset"
]

# Minimal, VS Code light/dark–friendly SVGs (stroke/fill = currentColor)
# Each icon is ~24x24, simple geometry for clarity at small sizes.
ICONS: Dict[str, str] = {
    "diagram": (
        '<svg viewBox="0 0 24 24" width="20" height="20" xmlns="http://www.w3.org/2000/svg">'
        '<g fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">'
        '<circle cx="6" cy="6" r="2"/><circle cx="18" cy="6" r="2"/><circle cx="12" cy="18" r="2"/>'
        '<path d="M8 6h6M12 8v8M16 6h2"/></g></svg>'
    ),
    "pat": (
        '<svg viewBox="0 0 24 24" width="20" height="20" xmlns="http://www.w3.org/2000/svg">'
        '<g fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M4 5h12M4 9h8M4 13h10M4 17h6"/></g></svg>'
    ),
    "dam": (
        '<svg viewBox="0 0 24 24" width="20" height="20" xmlns="http://www.w3.org/2000/svg">'
        '<g fill="none" stroke="currentColor" stroke-width="1.6"><rect x="4" y="4" width="16" height="16" rx="2"/>'
        '<path d="M12 4v16M4 12h16"/></g></svg>'
    ),
    "contract": (
        '<svg viewBox="0 0 24 24" width="20" height="20" xmlns="http://www.w3.org/2000/svg">'
        '<g fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round">'
        '<path d="M7 4h7l4 4v12a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2z"/>'
        '<path d="M14 4v4h4"/><path d="M8 13h8M8 17h6"/></g></svg>'
    ),
    "model": (
        '<svg viewBox="0 0 24 24" width="20" height="20" xmlns="http://www.w3.org/2000/svg">'
        '<g fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round">'
        '<rect x="3" y="5" width="6" height="6" rx="1"/><rect x="15" y="5" width="6" height="6" rx="1"/>'
        '<rect x="9" y="13" width="6" height="6" rx="1"/></g></svg>'
    ),
    "catalog": (
        '<svg viewBox="0 0 24 24" width="20" height="20" xmlns="http://www.w3.org/2000/svg">'
        '<g fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round">'
        '<path d="M5 4h10a2 2 0 0 1 2 2v14H7a2 2 0 0 1-2-2V4z"/><path d="M7 8h8"/></g></svg>'
    ),
    "workflow": (
        '<svg viewBox="0 0 24 24" width="20" height="20" xmlns="http://www.w3.org/2000/svg">'
        '<g fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">'
        '<rect x="4" y="4" width="6" height="4" rx="1"/><rect x="14" y="10" width="6" height="4" rx="1"/>'
        '<rect x="4" y="16" width="6" height="4" rx="1"/><path d="M10 6h4M7 8v8M14 12h-4"/></g></svg>'
    ),
    "security": (
        '<svg viewBox="0 0 24 24" width="20" height="20" xmlns="http://www.w3.org/2000/svg">'
        '<g fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round">'
        '<path d="M12 3l7 3v5c0 5-3.5 8.5-7 10-3.5-1.5-7-5-7-10V6l7-3z"/></g></svg>'
    ),
    "data": (
        '<svg viewBox="0 0 24 24" width="20" height="20" xmlns="http://www.w3.org/2000/svg">'
        '<g fill="none" stroke="currentColor" stroke-width="1.6"><ellipse cx="12" cy="6" rx="7" ry="3"/>'
        '<path d="M5 6v6c0 1.7 3.1 3 7 3s7-1.3 7-3V6M5 12v6c0 1.7 3.1 3 7 3s7-1.3 7-3v-6"/></g></svg>'
    ),
    "infra": (
        '<svg viewBox="0 0 24 24" width="20" height="20" xmlns="http://www.w3.org/2000/svg">'
        '<g fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M6 16h12a2 2 0 0 1 0 4H6a2 2 0 0 1 0-4z"/><path d="M8 16V8a4 4 0 0 1 8 0v8"/></g></svg>'
    ),
    "obs": (
        '<svg viewBox="0 0 24 24" width="20" height="20" xmlns="http://www.w3.org/2000/svg">'
        '<g fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">'
        '<circle cx="12" cy="12" r="7"/><circle cx="12" cy="12" r="2"/><path d="M12 5v2M12 17v2M5 12h2M17 12h2"/></g></svg>'
    ),
    "gov": (
        '<svg viewBox="0 0 24 24" width="20" height="20" xmlns="http://www.w3.org/2000/svg">'
        '<g fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M4 10h16l-8-6-8 6z"/><path d="M6 10v7M18 10v7"/><path d="M3 20h18"/></g></svg>'
    ),
    "risk": (
        '<svg viewBox="0 0 24 24" width="20" height="20" xmlns="http://www.w3.org/2000/svg">'
        '<g fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M10.3 4.5l-7 12A1.7 1.7 0 0 0 4.7 19h14.6a1.7 1.7 0 0 0 1.4-2.5l-7-12a1.7 1.7 0 0 0-2.9 0z"/>'
        '<path d="M12 9v4M12 16h.01"/></g></svg>'
    ),
    "ops": (
        '<svg viewBox="0 0 24 24" width="20" height="20" xmlns="http://www.w3.org/2000/svg">'
        '<g fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M14 7l3 3-7 7H7v-3l7-7z"/><circle cx="17" cy="7" r="1.5"/></g></svg>'
    ),
    "finops": (
        '<svg viewBox="0 0 24 24" width="20" height="20" xmlns="http://www.w3.org/2000/svg">'
        '<g fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round">'
        '<path d="M6 8c0-2.2 2.2-4 6-4s6 1.8 6 4-2.2 4-6 4-6 1.8-6 4 2.2 4 6 4 6-1.8 6-4"/><path d="M12 4v16"/></g></svg>'
    ),
    "qa": (
        '<svg viewBox="0 0 24 24" width="20" height="20" xmlns="http://www.w3.org/2000/svg">'
        '<g fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M4 20l2-6h12l2 6"/><path d="M8 14l2-10h4l2 10"/></g></svg>'
    ),
    "perf": (
        '<svg viewBox="0 0 24 24" width="20" height="20" xmlns="http://www.w3.org/2000/svg">'
        '<g fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M20 13a8 8 0 1 0-16 0"/><path d="M12 13l4-4"/></g></svg>'
    ),
    "asset": (
        '<svg viewBox="0 0 24 24" width="20" height="20" xmlns="http://www.w3.org/2000/svg">'
        '<g fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round">'
        '<rect x="3" y="4" width="8" height="6" rx="1"/><rect x="13" y="4" width="8" height="6" rx="1"/>'
        '<rect x="8" y="14" width="8" height="6" rx="1"/><path d="M7 10v4M17 10v4"/></g></svg>'
    ),
}

def _build_doc(key: str, name: str, description: str, icon_svg: str) -> dict:
    now = datetime.utcnow()
    return {
        "_id": f"cat:{key}",
        "key": key,
        "name": name,
        "description": description,
        "icon_svg": icon_svg,
        "created_at": now,
        "updated_at": now,
    }

def _default_name(key: str) -> str:
    return key.replace("_", " ").title()

def _default_description(key: str) -> str:
    return f"Category for CAM artifacts with key '{key}'."

async def ensure_categories_seed(db: AsyncIOMotorDatabase) -> dict:
    await ensure_indexes(db)
    col = db["cam_categories"]

    existing_keys = set()
    async for d in col.find({}, {"key": 1, "_id": 0}):
        if "key" in d:
            existing_keys.add(d["key"])

    to_seed = [k for k in CATEGORY_KEYS if k not in existing_keys]
    seeded = 0
    for key in to_seed:
        name = _default_name(key)
        desc = _default_description(key)
        icon = ICONS.get(key) or ICONS["diagram"]
        await col.insert_one(_build_doc(key, name, desc, icon))
        seeded += 1

    return {"existing": len(existing_keys), "seeded": seeded, "total": len(CATEGORY_KEYS)}
