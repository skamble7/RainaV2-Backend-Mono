# services/artifact-service/app/seeds/bootstrap.py
from __future__ import annotations

import logging
from typing import Dict, Any, Set

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.dal.kind_registry_dal import KINDS, upsert_kind, ensure_registry_indexes
from app.seeds.seed_registry import ALL_KINDS, build_kind_doc

log = logging.getLogger(__name__)

async def ensure_registry_seed(db: AsyncIOMotorDatabase) -> Dict[str, Any]:
    """
    Idempotent seeding:
      - If the kind_registry collection is empty: seed all kinds.
      - If partially populated: seed only missing kinds.
      - If fully populated: no-op.
    Returns metadata for logs.
    """
    await ensure_registry_indexes(db)
    col = db[KINDS]

    existing: Set[str] = set()
    async for d in col.find({}, {"_id": 1}):
        existing.add(d["_id"])

    missing = [k for k in ALL_KINDS if k not in existing]

    if not existing and not missing:
        # edge case: no kinds configured in ALL_KINDS (shouldn't happen)
        return {"mode": "skip", "existing": 0, "seeded": 0}

    if not existing:
        mode = "fresh"
    elif missing:
        mode = "partial"
    else:
        mode = "skip"

    seeded = 0
    for k in missing:
        doc = build_kind_doc(k)
        await upsert_kind(db, doc)
        seeded += 1

    log.info("Kind registry seed: mode=%s existing=%d seeded=%d", mode, len(existing), seeded)
    return {"mode": mode, "existing": len(existing), "seeded": seeded}
