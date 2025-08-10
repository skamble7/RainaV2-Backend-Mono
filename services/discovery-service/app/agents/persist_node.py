from app.models.state import DiscoveryState
from app.clients.artifact_service import create_artifact
from app.artifacts.adapters import ADAPTERS, ALLOWED_KINDS

def pick_kind(art: dict, step_id: str | None, state: DiscoveryState) -> str:
    # If the artifact already declares a supported kind, keep it
    k = (art.get("kind") or "").strip()
    if k in ALLOWED_KINDS:
        return k
    # Else try the step's capability 'produces_kinds'
    meta = state.get("context", {}).get("step_cap_meta", {}).get(step_id or "", {})
    pk = meta.get("produces_kinds") or []
    for candidate in pk:
        if candidate in ALLOWED_KINDS:
            return candidate
    # Fallback
    return "cam.document"

async def persist_node(state: DiscoveryState) -> DiscoveryState:
    if not state.get("artifacts"):
        return state

    ctx = {
        "workspace_id": state["workspace_id"],
        "playbook_id": state["playbook_id"],
    }
    ids, failures = [], []

    for raw in state["artifacts"]:
        if state.get("context", {}).get("dry_run"):
            continue
        step_id = raw.get("_step_id") if isinstance(raw, dict) else None
        # choose a kind and route to the adapter
        kind = pick_kind(raw, step_id, state)
        raw["kind"] = kind
        adapter = ADAPTERS.get(kind) or ADAPTERS["*"]
        try:
            artifact = adapter.normalize(raw, ctx)
            resp = await create_artifact(state["workspace_id"], artifact)
            ids.append(resp.get("artifact_id") or resp.get("id"))
        except Exception as e:
            failures.append({"error": str(e), "kind": kind, "name": raw.get("name")})

    state.setdefault("context", {})["artifact_ids"] = ids
    state.setdefault("context", {})["artifact_failures"] = failures
    state.setdefault("logs", []).append(f"Persisted {len(ids)} artifacts; failures={len(failures)}")

    if not ids and failures:
        raise RuntimeError(f"All artifact persists failed: {failures[:2]} ...")
    return state
