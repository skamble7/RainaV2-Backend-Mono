from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from app.models.state import DiscoveryState
from app.clients.artifact_service import create_artifact
from app.artifacts.adapters import ADAPTERS, ALLOWED_KINDS


def pick_kind(art: dict, step_id: Optional[str], state: DiscoveryState) -> str:
    """
    Decide the artifact 'kind' to persist.
    Priority:
      1) Explicit kind on the artifact (if allowed)
      2) Step capability's 'produces_kinds' (first allowed)
      3) Fallback: 'cam.document'
    """
    # 1) Keep explicit kind if valid
    k = (art.get("kind") or "").strip()
    if k in ALLOWED_KINDS:
        return k

    # 2) Use produces_kinds from the step's capability metadata
    meta = state.get("context", {}).get("step_cap_meta", {}).get(step_id or "", {})
    for candidate in meta.get("produces_kinds") or []:
        if candidate in ALLOWED_KINDS:
            return candidate

    # 3) Fallback
    return "cam.document"


def _stamp_provenance(raw: Dict[str, Any], state: DiscoveryState) -> None:
    """
    Add a lightweight provenance note to the artifact payload in-place.
    Safe to call multiple times; appends to the list.
    """
    prov = {
        "agent_id": raw.get("_agent_id"),  # set by agent runner
        "playbook_id": state.get("playbook_id"),
        "model_id": state.get("model_id"),
        "pack": {
            "key": state.get("context", {}).get("pack_key"),
            "version": state.get("context", {}).get("pack_version"),
        },
        # Optional fingerprint(s) – populate upstream later if desired
        "inputs_fingerprint": state.get("inputs_hash"),
        "ts": time.time(),
    }
    raw.setdefault("provenance", [])
    raw["provenance"].append(prov)


async def persist_node(state: DiscoveryState) -> DiscoveryState:
    """
    Persists artifacts accumulated on the state into the artifact-service.
    - Chooses/normalizes 'kind'
    - Stamps provenance
    - Routes to the appropriate adapter
    - Collects persisted IDs and failures on state.context
    """
    artifacts = state.get("artifacts") or []
    if not artifacts:
        return state

    ctx = {
        "workspace_id": state["workspace_id"],
        "playbook_id": state["playbook_id"],
    }
    ids: List[str] = []
    failures: List[Dict[str, Any]] = []

    for raw in artifacts:
        # Honor dry-run early
        if state.get("context", {}).get("dry_run"):
            state.setdefault("logs", []).append("persist_node: dry_run=true, skipping persist")
            continue

        step_id: Optional[str] = raw.get("_step_id") if isinstance(raw, dict) else None

        # Decide and set kind (adapter routing relies on this)
        kind = pick_kind(raw, step_id, state)
        raw["kind"] = kind

        # Guardrails (fail-fast with clear messages)
        name = raw.get("name")
        data = raw.get("data")
        if not isinstance(name, str) or not name.strip():
            failures.append({"error": "artifact.name is required", "kind": kind, "name": name})
            continue
        if not isinstance(data, dict):
            failures.append({"error": "artifact.data must be an object", "kind": kind, "name": name})
            continue

        # Stamp provenance (Phase 1: minimal but useful)
        _stamp_provenance(raw, state)

        adapter = (ADAPTERS.get(kind) or ADAPTERS["*"])

        try:
            artifact_payload = adapter.normalize(raw, ctx)
            resp = await create_artifact(state["workspace_id"], artifact_payload)
            persisted_id = resp.get("artifact_id") or resp.get("id")
            if persisted_id:
                ids.append(persisted_id)
            else:
                failures.append({"error": "no id returned from artifact-service", "kind": kind, "name": name})
        except Exception as e:
            failures.append({"error": str(e), "kind": kind, "name": name})

    state.setdefault("context", {})["artifact_ids"] = ids
    state.setdefault("context", {})["artifact_failures"] = failures
    state.setdefault("logs", []).append(
        f"Persisted {len(ids)} artifacts; failures={len(failures)}"
    )

    if not ids and failures:
        # Surface first couple of failures for quick diagnosis
        sample = failures[:2]
        raise RuntimeError(f"All artifact persists failed: {sample}")

    return state
