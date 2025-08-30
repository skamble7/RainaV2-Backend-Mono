from __future__ import annotations

from typing import Any, Dict, List

from app.models.state import DiscoveryState
from app.artifacts.adapters import normalize_for_persist, is_supported_kind
from app.clients import artifact_service


def _to_create_items(artifacts: List[Dict[str, Any]], ctx: Dict[str, Any]) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for cam in artifacts or []:
        if not isinstance(cam, dict):
            cam = {"kind": ctx.get("kind") or "cam.document", "name": "Generated", "data": cam}

        if not is_supported_kind(cam.get("kind") or ctx.get("kind") or ""):
            continue

        env = normalize_for_persist(cam, ctx)
        kind = env["kind"]
        name = env["name"] or kind

        items.append(
            {
                "kind": kind,
                "name": name,
                "data": env.get("data"),
                "natural_key": f"{kind}:{name}".lower().strip(),
                "provenance": {
                    "source": env.get("metadata", {}).get("source") or "discovery-service",
                    "run_id": ctx.get("run_id"),
                    "playbook_id": ctx.get("playbook_id"),
                },
            }
        )
    return items


async def persist_node(state: DiscoveryState) -> DiscoveryState:
    """Upsert generated artifacts; resilient and side-effect free on failure."""
    ctx = state.get("context") or {}
    workspace_id = state.get("workspace_id")
    run_id = ctx.get("run_id")

    artifacts = state.get("artifacts") or []
    items = _to_create_items(artifacts, {**ctx, "workspace_id": workspace_id})

    if not items:
        ctx.setdefault("artifact_ids", [])
        state["context"] = ctx
        return state

    failures: List[Dict[str, Any]] = []
    saved_ids: List[str] = []

    try:
        resp = await artifact_service.upsert_batch(str(workspace_id), items, run_id=str(run_id) if run_id else None)
        # Handle several plausible response shapes
        if isinstance(resp, dict):
            if isinstance(resp.get("items"), list):
                for it in resp["items"]:
                    a = it.get("artifact") or it
                    aid = a.get("artifact_id") or a.get("id") or a.get("_id")
                    if aid:
                        saved_ids.append(str(aid))
            elif isinstance(resp.get("results"), list):
                for r in resp["results"]:
                    aid = r.get("artifact_id") or r.get("id") or r.get("_id")
                    if aid:
                        saved_ids.append(str(aid))
        elif isinstance(resp, list):
            for a in resp:
                if isinstance(a, dict):
                    aid = a.get("artifact_id") or a.get("id") or a.get("_id")
                    if aid:
                        saved_ids.append(str(aid))
    except Exception as e:
        failures.append({"error": str(e), "count": len(items)})

    # Fallback to single item upserts if batch didn't return anything and didn't error
    if not saved_ids and not failures:
        for it in items:
            try:
                r = await artifact_service.upsert_single(str(workspace_id), it, run_id=str(run_id) if run_id else None)
                if isinstance(r, dict):
                    aid = r.get("artifact_id") or r.get("id") or r.get("_id") or (r.get("artifact") or {}).get("artifact_id")
                    if aid:
                        saved_ids.append(str(aid))
            except Exception as e:
                failures.append({"name": it.get("name"), "kind": it.get("kind"), "error": str(e)})

    ctx.setdefault("artifact_failures", [])
    ctx["artifact_failures"].extend(failures)
    ctx["artifact_ids"] = saved_ids
    state["context"] = ctx
    return state
