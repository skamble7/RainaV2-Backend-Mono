from __future__ import annotations

from typing import Any, Dict

from app.models.state import DiscoveryState
from app.infra.rabbit import publish_event_v1


def _safe_counts(ctx: Dict[str, Any]) -> Dict[str, int]:
    counts = (ctx or {}).get("delta_counts") or {}
    return {
        "new": int(counts.get("new", 0)),
        "updated": int(counts.get("updated", 0)),
        "unchanged": int(counts.get("unchanged", 0)),
        "retired": int(counts.get("retired", 0)),
        "deleted": int(counts.get("deleted", 0)),
    }


async def publish_node(state: DiscoveryState) -> DiscoveryState:
    ctx = state.get("context") or {}
    payload = {
        "run_id": (ctx or {}).get("run_id"),
        "workspace_id": state.get("workspace_id"),
        "playbook_id": state.get("playbook_id"),
        "artifact_ids": list((ctx or {}).get("artifact_ids") or []),
        "artifact_failures": list((ctx or {}).get("artifact_failures") or []),
        "validations": state.get("validations") or [],
        "deltas": {"counts": _safe_counts(ctx)},
    }
    publish_event_v1(org="raina", event="completed", payload=payload, headers={})
    return state
