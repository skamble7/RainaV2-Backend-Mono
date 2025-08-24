# services/capability-service/app/routers/capability_routes.py
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Response, status
from fastapi.responses import ORJSONResponse

from ..config import settings
from ..db.mongodb import get_db
from ..events.rabbit import publish_event_v1
from ..dal import capability_dal as dal
from ..models.capability_pack import CapabilityPackCreate, CapabilityPackUpdate
from libs.raina_common.events import Service  # service segment for versioned keys

router = APIRouter(
    prefix="/capability",
    tags=["capability"],
    default_response_class=ORJSONResponse,
)

def _org() -> str:
    # org/tenant segment for the routing key; defaults to "raina"
    return settings.events_org

@router.post("/pack", status_code=status.HTTP_201_CREATED)
async def create_pack(body: CapabilityPackCreate):
    db = await get_db()
    existing = await dal.get_pack(db, body.key, body.version)
    if existing:
        raise HTTPException(status_code=409, detail="Capability pack with key+version exists")

    pack = await dal.create_pack(db, body)

    # raina.capability.pack.created.v1
    publish_event_v1(
        org=_org(),
        event="pack.created",
        payload={"key": pack.key, "version": pack.version},
    )
    return pack

@router.get("/pack/{key}/{version}")
async def get_pack(key: str, version: str):
    db = await get_db()
    pack = await dal.get_pack(db, key, version)
    if not pack:
        raise HTTPException(status_code=404, detail="Not found")
    return pack

@router.get("/packs")
async def list_packs(
    key: str | None = Query(default=None),
    q: str | None = Query(default=None, description="full-text search"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    db = await get_db()
    return await dal.list_packs(db, key, q, limit, offset)

@router.put("/pack/{key}/{version}")
async def update_pack(key: str, version: str, body: CapabilityPackUpdate):
    db = await get_db()
    pack = await dal.upsert_pack(db, key, version, body)
    if not pack:
        raise HTTPException(status_code=404, detail="Not found")

    # raina.capability.pack.updated.v1
    publish_event_v1(
        org=_org(),
        event="pack.updated",
        payload={"key": key, "version": version},
    )
    return pack

@router.delete("/pack/{key}/{version}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_pack(key: str, version: str):
    db = await get_db()
    ok = await dal.delete_pack(db, key, version)
    if not ok:
        raise HTTPException(status_code=404, detail="Not found")

    # raina.capability.pack.deleted.v1
    publish_event_v1(
        org=_org(),
        event="pack.deleted",
        payload={"key": key, "version": version},
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)

# Convenience: list playbooks for a pack
@router.get("/pack/{key}/{version}/playbooks")
async def list_playbooks(key: str, version: str):
    db = await get_db()
    pack = await dal.get_pack(db, key, version)
    if not pack:
        raise HTTPException(status_code=404, detail="Not found")
    return pack.playbooks
