# services/discovery-service/app/agents/publish_node.py
from __future__ import annotations

from typing import Dict
from app.models.state import DiscoveryState
from app.infra.rabbit import publish_event_v1

def _counts_from_diff(state: DiscoveryState) -> Dict[str, int]:
    diff = state.get("artifacts_diff") or {}
    if isinstance(diff.get("counts"), dict):
        # Prefer the counts computed by classify_node if present
        c = diff["counts"]
        return {
            "new": int(c.get("new", 0)),
            "updated": int(c.get("updated", 0)),
            "unchanged": int(c.get("unchanged", 0)),
            "retired": int(c.get("retired", 0)),
        }
    return {
        "new": len(diff.get("new", []) or []),
        "updated": len(diff.get("updated", []) or []),
        "unchanged": len(diff.get("unchanged", []) or []),
        "retired": len(diff.get("retired", []) or []),
    }

async def publish_node(state: DiscoveryState) -> DiscoveryState:
    counts = _counts_from_diff(state)
    state["deltas"] = {"counts": dict(counts)}  # authoritative from classify_node

    ctx = state.get("context") or {}
    payload = {
        "run_id": (ctx or {}).get("run_id"),
        "workspace_id": state.get("workspace_id"),
        "playbook_id": state.get("playbook_id"),
        "artifact_ids": list((ctx or {}).get("artifact_ids") or []),
        "artifact_failures": list((ctx or {}).get("artifact_failures") or []),
        "validations": state.get("validations") or [],
        "deltas": {"counts": dict(counts)},
    }
    publish_event_v1(org="raina", event="completed", payload=payload, headers={})
    return state
