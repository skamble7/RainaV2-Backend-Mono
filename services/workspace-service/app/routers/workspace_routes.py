# app/routers/workspace_routes.py
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from typing import Dict, Any
from app.db.mongodb import get_db
from app.dal.workspace_dal import (
    create_workspace, get_workspace, list_workspaces, update_workspace, delete_workspace, merge_platform_config,
)
from app.models.workspace import Workspace, WorkspaceCreate, WorkspaceUpdate, AccessLevel
from app.events.rabbit import publish_event
from app.config import settings

router = APIRouter(prefix="/workspace", tags=["workspace"])


def rk(event: str) -> str:
    """Build versioned routing key with org segment from settings."""
    return f"{settings.EVENTS_ORG}.workspace.{event}.v1"


def _infer_origin_platform(request: Request, payload: WorkspaceCreate) -> str:
    # Priority: explicit payload > header > default
    if payload.origin_platform:
        return payload.origin_platform.lower()
    hdr = request.headers.get(settings.PLATFORM_HEADER)
    if hdr:
        return hdr.lower()
    return settings.DEFAULT_ORIGIN_PLATFORM.lower()


@router.post("/", response_model=Workspace, status_code=201)
async def create_ws(payload: WorkspaceCreate, request: Request, db=Depends(get_db)):
    # Inject minimal defaults
    origin_platform = _infer_origin_platform(request, payload)
    if not payload.visibility:
        payload.visibility = {origin_platform: AccessLevel.owner}
    if not payload.origin_platform:
        payload.origin_platform = origin_platform

    ws = await create_workspace(db, payload)
    await publish_event(rk("created"), ws.model_dump(by_alias=True))
    return ws


@router.get("/", response_model=list[Workspace])
async def list_ws(q: str | None = Query(None, description="Search by name"), db=Depends(get_db)):
    return await list_workspaces(db, q)


@router.get("/{wid}", response_model=Workspace)
async def get_ws(wid: str, db=Depends(get_db)):
    ws = await get_workspace(db, wid)
    if not ws:
        raise HTTPException(404, detail="Workspace not found")
    return ws


@router.put("/{wid}", response_model=Workspace)
async def update_ws(wid: str, patch: WorkspaceUpdate, db=Depends(get_db)):
    ws = await update_workspace(db, wid, patch)
    if not ws:
        raise HTTPException(404, detail="Workspace not found")
    await publish_event(rk("updated"), ws.model_dump(by_alias=True))
    return ws


@router.delete("/{wid}", status_code=204)
async def delete_ws_route(wid: str, db=Depends(get_db)):
    ok = await delete_workspace(db, wid)
    if not ok:
        raise HTTPException(404, detail="Workspace not found")
    await publish_event(rk("deleted"), {"_id": wid})
    return None


# -------- NEW: platform config endpoints -------------------------------------

@router.get("/{wid}/platform/{platform}/config", response_model=Dict[str, Any])
async def get_platform_cfg(wid: str, platform: str, db=Depends(get_db)):
    ws = await get_workspace(db, wid)
    if not ws:
        raise HTTPException(404, detail="Workspace not found")
    section = ws.platform_config.get(platform.lower(), None)
    return section.model_dump(exclude_none=True) if section else {}


@router.put("/{wid}/platform/{platform}/config", response_model=Workspace)
async def merge_platform_cfg(wid: str, platform: str, patch: Dict[str, Any], db=Depends(get_db)):
    """
    Merge the provided keys into the platform's config section.
    Example body (Renova after a successful learning run):
    {
      "context_ready": true,
      "last_successful_run_id": "run_123",
      "last_successful_run_at": "2025-09-07T12:34:56Z"
    }
    """
    ws = await merge_platform_config(db, wid, platform, patch)
    if not ws:
        raise HTTPException(404, detail="Workspace not found")

    # Emit a thin inter-platform event so Raina can react.
    await publish_event(
        rk("platform_config.updated"),
        {
            "_id": ws.id,
            "platform": platform.lower(),
            "config": ws.platform_config.get(platform.lower(), {}).model_dump(exclude_none=True),
            "origin_platform": ws.origin_platform,
        },
    )
    return ws
