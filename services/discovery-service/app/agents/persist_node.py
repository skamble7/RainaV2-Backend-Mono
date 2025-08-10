from app.models.state import DiscoveryState
from app.clients.artifact_service import create_artifact
from datetime import datetime

ALLOWED_KINDS = {
    "cam.document",
    "cam.context_map",
    "cam.capability_model",
    "cam.service_contract",
    "cam.sequence_diagram",
    "cam.erd",
    "cam.adr_index",
}

def guess_kind(cam: dict) -> str:
    # Respect if already allowed
    k = (cam.get("kind") or cam.get("type") or "").strip().lower()
    if k in ALLOWED_KINDS:
        return k
    # Heuristics based on content
    text = (cam.get("title") or cam.get("name") or "").lower()
    data = cam.get("data") or cam
    if "sequence" in k or "sequence" in text:
        return "cam.sequence_diagram"
    if "service" in k or "service" in text or "candidate_services" in json_safe_keys(data):
        return "cam.service_contract"
    # Fallback
    return "cam.document"

def json_safe_keys(x):
    try:
        if isinstance(x, dict): return x.keys()
    except Exception:
        pass
    return []

def normalize_artifact(cam: dict, workspace_id: str, playbook_id: str) -> dict:
    """
    Normalize LLM output into the envelope artifact-service expects.
    Ensures: schema_version, kind (allowed), name, data.
    """
    # Pull potential fields
    schema_version = str(cam.get("schema_version") or "1.0")
    kind = guess_kind(cam)
    # Prefer explicit name/title; else derive
    name = cam.get("name") or cam.get("title")
    if not name:
        # Try from candidate services or a sensible default
        if isinstance(cam, dict) and "data" in cam:
            ds = cam["data"]
            if isinstance(ds, dict) and "outputs" in ds and "candidate_services" in ds["outputs"]:
                name = "Service Contracts (Discovered)"
        if not name:
            name = f"{kind.replace('cam.', '').replace('_', ' ').title()} (Generated)"

    # Data payload: if the model already wrapped in {"data": ...}, use that
    data = cam.get("data") if isinstance(cam, dict) else cam
    if data is None:
        data = cam  # last resort

    # Move any descriptive metadata up if present
    meta = cam.get("metadata", {})
    description = cam.get("description") or meta.get("description")

    artifact = {
        "schema_version": schema_version,
        "kind": kind,                 # MUST be one of the allowed kinds
        "name": name,                 # REQUIRED by artifact-service
        "title": cam.get("title") or name,
        "version": cam.get("version") or 1,
        "tags": cam.get("tags") or ["generated", "discovery"],
        "metadata": {
            **meta,
            "description": description or meta.get("description"),
            "workspace_id": workspace_id,
            "source": "discovery-service",
            "playbook_id": playbook_id,
            "generated_at": datetime.utcnow().isoformat() + "Z",
        },
        "data": data,
    }
    return artifact

async def persist_node(state: DiscoveryState) -> DiscoveryState:
    if not state.get("artifacts"):
        return state

    ids, failures = [], []
    ws = state["workspace_id"]
    pb = state["playbook_id"]

    for cam in state["artifacts"]:
        if state.get("context", {}).get("dry_run"):
            continue
        try:
            artifact = normalize_artifact(cam, ws, pb)
            resp = await create_artifact(ws, artifact)
            ids.append(resp.get("artifact_id") or resp.get("id"))
        except Exception as e:
            failures.append({"error": str(e), "preview": {"kind": artifact.get("kind"), "name": artifact.get("name")}})
            continue

    state.setdefault("context", {})["artifact_ids"] = ids
    state.setdefault("context", {})["artifact_failures"] = failures
    state.setdefault("logs", []).append(f"Persisted {len(ids)} artifacts; failures={len(failures)}")

    if not ids and failures:
        raise RuntimeError(f"All artifact persists failed: {failures[:2]} ...")

    return state
