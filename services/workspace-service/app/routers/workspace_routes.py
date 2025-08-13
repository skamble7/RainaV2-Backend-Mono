# app/routes/workspace_routes.py
from fastapi import APIRouter, Depends, HTTPException, Query
from app.db.mongodb import get_db
from app.dal.workspace_dal import (
    create_workspace, get_workspace, list_workspaces, update_workspace, delete_workspace,
)
from app.models.workspace import Workspace, WorkspaceCreate, WorkspaceUpdate
from app.events.rabbit import publish_event
from app.config import settings

router = APIRouter(prefix="/workspace", tags=["workspace"])


def rk(event: str) -> str:
    """Build versioned routing key with org segment."""
    return f"{settings.EVENTS_ORG}.workspace.{event}.v1"


@router.post("/", response_model=Workspace, status_code=201)
async def create_ws(payload: WorkspaceCreate, db=Depends(get_db)):
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
