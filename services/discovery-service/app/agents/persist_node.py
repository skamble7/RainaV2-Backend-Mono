#services/discovery-service/app/agents/persist_node.py
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
                # natural_key is ignored by the new API (server computes),
                # but sending it remains harmless for older versions:
                "natural_key": f"{kind}:{name}".lower().strip(),
                "schema_version": env.get("schema_version"),  # hint; server may migrate
                "provenance": {
                    # 'source' isn't in Provenance; it's ignored; keep it for analytics logs server-side if allowed
                    "author": env.get("metadata", {}).get("source") or "discovery-service",
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
    run_id = (ctx.get("run_id") or "") and str(ctx.get("run_id"))

    artifacts = state.get("artifacts") or []
    items = _to_create_items(artifacts, {**ctx, "workspace_id": workspace_id})

    logs = state.setdefault("logs", [])
    logs.append(f"Persist: prepared items={len(items)} from artifacts={len(artifacts)}")

    if not items:
        ctx.setdefault("artifact_ids", [])
        state["context"] = ctx
        logs.append("Persist: nothing to save (no supported artifacts)")
        return state

    failures: List[Dict[str, Any]] = []
    saved_ids: List[str] = []
    op_counts = {"insert": 0, "update": 0, "noop": 0, "failed": 0}

    try:
        resp = await artifact_service.upsert_batch(str(workspace_id), items, run_id=run_id or None)

        # New API: {"counts": {...}, "results": [...]}
        if isinstance(resp, dict) and isinstance(resp.get("results"), list):
            counts = resp.get("counts") or {}
            for k in ("insert", "update", "noop", "failed"):
                if isinstance(counts.get(k), int):
                    op_counts[k] = counts[k]

            for idx, r in enumerate(resp["results"]):
                if "error" in r:
                    failures.append({"index": idx, "error": r["error"]})
                    continue
                aid = r.get("artifact_id") or r.get("id") or r.get("_id")
                if aid:
                    saved_ids.append(str(aid))

        # Back-compat: some clients returned {"items":[...]} or a plain list
        elif isinstance(resp, dict) and isinstance(resp.get("items"), list):
            for it in resp["items"]:
                a = it.get("artifact") or it
                aid = a.get("artifact_id") or a.get("id") or a.get("_id")
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

    # Fallback to single upserts if batch yielded nothing and no explicit error
    if not saved_ids and not failures:
        for i, it in enumerate(items):
            try:
                r = await artifact_service.upsert_single(str(workspace_id), it, run_id=run_id or None)
                if isinstance(r, dict):
                    aid = r.get("artifact_id") or r.get("id") or r.get("_id") or (r.get("artifact") or {}).get("artifact_id")
                    if aid:
                        saved_ids.append(str(aid))
            except Exception as e:
                failures.append({"index": i, "name": it.get("name"), "kind": it.get("kind"), "error": str(e)})

    # Accumulate failures & ids into context
    ctx.setdefault("artifact_failures", [])
    ctx["artifact_failures"].extend(failures)
    ctx["artifact_ids"] = saved_ids
    state["context"] = ctx

    # Log summary (with counts if we got them)
    logs.append(
        f"Persist: saved={len(saved_ids)} failures={len(failures)}"
        + (f" counts={op_counts}" if any(op_counts.values()) else "")
    )
    if failures:
        # Keep it short; details are in context.artifact_failures
        sample = failures[0]
        logs.append(f"Persist: first failure sample={sample}")

    return state
