# app/agents/publish_node.py  (or wherever this node lives)
from __future__ import annotations

from app.infra.rabbit import publish_event_v1   # ← new API (versioned keys)
from app.config import settings
from app.models.state import DiscoveryState

async def publish_node(state: DiscoveryState) -> DiscoveryState:
    """
    Emits: raina.discovery.completed.v1
    (org segment comes from settings.EVENTS_ORG; defaults to "raina")
    """
    payload = {
        "workspace_id": state.get("workspace_id"),
        "playbook_id": state.get("playbook_id"),
        "run_id": state.get("context", {}).get("run_id"),
        "artifact_ids": state.get("context", {}).get("artifact_ids", []),
        "logs": state.get("logs", []),
        "validations": state.get("validations", []),
    }

    publish_event_v1(
        org=settings.EVENTS_ORG,
        event="completed",
        payload=payload,
    )
    return state
