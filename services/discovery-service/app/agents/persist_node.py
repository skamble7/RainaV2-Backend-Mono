from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Optional, Tuple

from app.models.state import DiscoveryState
from app.clients.artifact_service import upsert_batch
from app.artifacts.adapters import ADAPTERS, ALLOWED_KINDS


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────
def _canonical(obj: Dict[str, Any]) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))

def _sha256(s: str) -> str:
    import hashlib
    return hashlib.sha256(s.encode("utf-8")).hexdigest()

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


def _stamp_provenance(raw: Dict[str, Any], state: DiscoveryState) -> Dict[str, Any]:
    """
    Build a single structured provenance object.
    (artifact-service models expect a single Provenance object, not a list.)
    """
    # Prefer precomputed fingerprint if present on state; otherwise derive
    inputs = state.get("inputs") or {}
    inputs_fp = state.get("context", {}).get("inputs_fingerprint")
    if not inputs_fp:
        try:
            inputs_fp = _sha256(_canonical(inputs))
        except Exception:
            inputs_fp = None

    prov = {
        "run_id": state.get("context", {}).get("run_id"),
        "playbook_id": state.get("playbook_id"),
        "model_id": state.get("model_id"),
        "step": raw.get("_step_id"),
        "pack_key": state.get("context", {}).get("pack_key"),
        "pack_version": state.get("context", {}).get("pack_version"),
        "inputs_fingerprint": inputs_fp,
        "author": state.get("options", {}).get("initiated_by"),   # optional, if you pass it
        "agent": "svc_discovery",
        "reason": raw.get("_reason") or "discovery.persist",
    }
    return prov


# ─────────────────────────────────────────────────────────────
# Main persist node
# ─────────────────────────────────────────────────────────────
async def persist_node(state: DiscoveryState) -> DiscoveryState:
    """
    Persists artifacts accumulated on the state into artifact-service using
    the batch upsert endpoint with lineage-aware, versioned semantics.

    - Chooses/normalizes 'kind'
    - Stamps structured Provenance (single object)
    - Uses adapters to normalize shape (may add natural_key/fingerprint)
    - Calls HTTP batch upsert with X-Run-Id header
    - Collects persisted IDs and failures into state.context
    """
    artifacts = state.get("artifacts") or []
    if not artifacts:
        return state

    if state.get("context", {}).get("dry_run"):
        state.setdefault("logs", []).append("persist_node: dry_run=true, skipping persist")
        return state

    ctx = {
        "workspace_id": state["workspace_id"],
        "playbook_id": state["playbook_id"],
    }

    batch_items: List[Dict[str, Any]] = []
    local_validation_failures: List[Dict[str, Any]] = []

    for raw in artifacts:
        step_id: Optional[str] = raw.get("_step_id") if isinstance(raw, dict) else None

        # Decide and set kind (adapter routing relies on this)
        kind = pick_kind(raw, step_id, state)
        raw["kind"] = kind

        # Guardrails (fail-fast with clear messages)
        name = raw.get("name")
        data = raw.get("data")
        if not isinstance(name, str) or not name.strip():
            local_validation_failures.append({"error": "artifact.name is required", "kind": kind, "name": name})
            continue
        if not isinstance(data, dict):
            local_validation_failures.append({"error": "artifact.data must be an object", "kind": kind, "name": name})
            continue

        # Provenance (single structured object)
        prov = _stamp_provenance(raw, state)

        # Adapter normalize to ArtifactItemCreate shape
        adapter = (ADAPTERS.get(kind) or ADAPTERS["*"])
        item = adapter.normalize(
            {
                "kind": kind,
                "name": name,
                "data": data,
                # Optional inputs the adapter may use to compute natural_key/fingerprint
                "provenance": prov,
                "_step_id": step_id,
            },
            ctx,
        )

        # Ensure required fields exist after normalization
        if not isinstance(item, dict) or "kind" not in item or "name" not in item or "data" not in item:
            local_validation_failures.append({"error": "adapter produced invalid artifact payload", "kind": kind, "name": name})
            continue

        # Force provenance to be a single object (not list)
        item["provenance"] = prov

        batch_items.append(item)

    # Early exit if everything failed validation
    if not batch_items and local_validation_failures:
        state.setdefault("context", {})["artifact_ids"] = []
        state.setdefault("context", {})["artifact_failures"] = local_validation_failures
        first = local_validation_failures[:2]
        raise RuntimeError(f"All artifact normalize/validate failed: {first}")

    # Call artifact-service batch upsert
    run_id = state.get("context", {}).get("run_id")
    try:
        result = await upsert_batch(state["workspace_id"], batch_items, run_id=run_id)
    except Exception as e:
        # Propagate but keep enough context for diagnosis
        state.setdefault("context", {})["artifact_ids"] = []
        state.setdefault("context", {})["artifact_failures"] = [{"error": str(e)}]
        raise

    # Summarize results
    ids: List[str] = []
    failures: List[Dict[str, Any]] = list(local_validation_failures)

    for r in result.get("results", []):
        if "artifact_id" in r:
            ids.append(r["artifact_id"])
        elif "error" in r:
            failures.append({"error": r["error"]})

    counts = result.get("counts", {})
    state.setdefault("context", {})["artifact_ids"] = ids
    state.setdefault("context", {})["artifact_failures"] = failures

    state.setdefault("logs", []).append(
        f"persist_node: batch upsert completed "
        f"(insert={counts.get('insert',0)}, update={counts.get('update',0)}, "
        f"noop={counts.get('noop',0)}, failed={counts.get('failed',0)})"
    )

    # If nothing persisted and there are failures, escalate
    if not ids and failures:
        sample = failures[:2]
        raise RuntimeError(f"All artifact persists failed: {sample}")

    return state
