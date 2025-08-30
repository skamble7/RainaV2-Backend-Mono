#services/discovery-service/app/clients/artifact_service.py
from __future__ import annotations

import uuid
from typing import Optional, List, Dict, Any

import httpx

from app.config import settings

# Pull IDs from middleware if present (falls back to fresh UUIDs)
try:
    from app.middleware.correlation import request_id_var, correlation_id_var  # type: ignore
except Exception:  # pragma: no cover
    request_id_var = correlation_id_var = None  # type: ignore


def _corr_headers(extra: Optional[dict] = None) -> dict:
    """
    Standard outbound headers:
      - x-request-id / x-correlation-id (propagated or fresh)
      - plus any extras (e.g., {"X-Run-Id": "..."}).
    """
    rid = None
    cid = None
    try:
        rid = request_id_var.get() if request_id_var else None
        cid = correlation_id_var.get() if correlation_id_var else None
    except Exception:
        pass
    if not rid:
        rid = str(uuid.uuid4())
    if not cid:
        cid = rid
    base = {
        "x-request-id": rid,
        "x-correlation-id": cid,
    }
    if extra:
        base.update(extra)
    return base


# ─────────────────────────────────────────────────────────────
# New preferred endpoints (versioned upsert semantics)
# ─────────────────────────────────────────────────────────────
async def upsert_single(workspace_id: str, item: Dict[str, Any], *, run_id: Optional[str] = None) -> Dict[str, Any]:
    headers = _corr_headers({"X-Run-Id": run_id} if run_id else None)
    url = f"{settings.ARTIFACT_SERVICE_URL}/artifact/{workspace_id}"
    async with httpx.AsyncClient(timeout=settings.REQUEST_TIMEOUT_S, headers=headers) as client:
        r = await client.post(url, json=item)
        if r.is_error:
            raise httpx.HTTPStatusError(f"{r.status_code}: {r.text}", request=r.request, response=r)
        return r.json()


async def upsert_batch(workspace_id: str, items: List[Dict[str, Any]], *, run_id: Optional[str] = None) -> Dict[str, Any]:
    headers = _corr_headers({"X-Run-Id": run_id} if run_id else None)
    url = f"{settings.ARTIFACT_SERVICE_URL}/artifact/{workspace_id}/upsert-batch"
    payload = {"items": items}
    async with httpx.AsyncClient(timeout=settings.REQUEST_TIMEOUT_S, headers=headers) as client:
        r = await client.post(url, json=payload)
        if r.is_error:
            raise httpx.HTTPStatusError(f"{r.status_code}: {r.text}", request=r.request, response=r)
        return r.json()


# ─────────────────────────────────────────────────────────────
# Legacy helpers (kept for convenience; now map to upsert)
# ─────────────────────────────────────────────────────────────
async def create_artifact(workspace_id: str, artifact: dict, *, idempotency_key: Optional[str] = None) -> dict:
    headers = _corr_headers()
    if idempotency_key:
        headers["idempotency-key"] = idempotency_key
    url = f"{settings.ARTIFACT_SERVICE_URL}/artifact/{workspace_id}"
    async with httpx.AsyncClient(timeout=settings.REQUEST_TIMEOUT_S, headers=headers) as client:
        r = await client.post(url, json=artifact)
        if r.is_error:
            raise httpx.HTTPStatusError(f"{r.status_code}: {r.text}", request=r.request, response=r)
        return r.json()


async def head_artifact(workspace_id: str, artifact_id: str) -> str | None:
    headers = _corr_headers()
    async with httpx.AsyncClient(timeout=settings.REQUEST_TIMEOUT_S, headers=headers) as client:
        r = await client.head(f"{settings.ARTIFACT_SERVICE_URL}/artifact/{workspace_id}/{artifact_id}")
        return r.headers.get("ETag")


# ─────────────────────────────────────────────────────────────
# Baseline inputs (NEW)
# ─────────────────────────────────────────────────────────────
async def set_inputs_baseline(
    workspace_id: str,
    inputs: Dict[str, Any],
    *,
    run_id: Optional[str] = None,
    if_absent_only: bool = False,
    expected_version: Optional[int] = None,
) -> Dict[str, Any]:
    headers = _corr_headers({"X-Run-Id": run_id} if run_id else None)
    q = []
    if if_absent_only:
        q.append("if_absent_only=true")
    if expected_version is not None:
        q.append(f"expected_version={expected_version}")
    qs = ("?" + "&".join(q)) if q else ""
    url = f"{settings.ARTIFACT_SERVICE_URL}/artifact/{workspace_id}/baseline-inputs{qs}"
    async with httpx.AsyncClient(timeout=settings.REQUEST_TIMEOUT_S, headers=headers) as client:
        r = await client.post(url, json=inputs)
        if r.is_error:
            raise httpx.HTTPStatusError(f"{r.status_code}: {r.text}", request=r.request, response=r)
        return r.json()


async def patch_inputs_baseline(
    workspace_id: str,
    *,
    avc: Optional[Dict[str, Any]] = None,
    pss: Optional[Dict[str, Any]] = None,
    fss_stories_upsert: Optional[List[Dict[str, Any]]] = None,
    run_id: Optional[str] = None,
    expected_version: Optional[int] = None,
) -> Dict[str, Any]:
    headers = _corr_headers({"X-Run-Id": run_id} if run_id else None)
    q = []
    if expected_version is not None:
        q.append(f"expected_version={expected_version}")
    qs = ("?" + "&".join(q)) if q else ""
    url = f"{settings.ARTIFACT_SERVICE_URL}/artifact/{workspace_id}/baseline-inputs{qs}"
    payload = {
        "avc": avc,
        "pss": pss,
        "fss_stories_upsert": fss_stories_upsert,
    }
    async with httpx.AsyncClient(timeout=settings.REQUEST_TIMEOUT_S, headers=headers) as client:
        r = await client.patch(url, json=payload)
        if r.is_error:
            raise httpx.HTTPStatusError(f"{r.status_code}: {r.text}", request=r.request, response=r)
        return r.json()


# ─────────────────────────────────────────────────────────────
# Helpful getters we use for diffing
# ─────────────────────────────────────────────────────────────
async def get_workspace_parent(workspace_id: str) -> Dict[str, Any]:
    """Fetches the parent/workspace doc (baseline inputs, last_promoted_run_id, etc.)."""
    headers = _corr_headers()
    url = f"{settings.ARTIFACT_SERVICE_URL}/artifact/{workspace_id}/parent"
    async with httpx.AsyncClient(timeout=settings.REQUEST_TIMEOUT_S, headers=headers) as client:
        r = await client.get(url)
        if r.status_code == 404:
            return {}
        if r.is_error:
            raise httpx.HTTPStatusError(f"{r.status_code}: {r.text}", request=r.request, response=r)
        return r.json()


async def get_artifact(workspace_id: str, artifact_id: str) -> Dict[str, Any]:
    """Fetch a single artifact document (we need natural_key/kind/name/fingerprint)."""
    headers = _corr_headers()
    url = f"{settings.ARTIFACT_SERVICE_URL}/artifact/{workspace_id}/{artifact_id}"
    async with httpx.AsyncClient(timeout=settings.REQUEST_TIMEOUT_S, headers=headers) as client:
        r = await client.get(url)
        if r.is_error:
            raise httpx.HTTPStatusError(f"{r.status_code}: {r.text}", request=r.request, response=r)
        return r.json()


async def get_artifacts_by_ids(workspace_id: str, ids: List[str]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for a_id in ids:
        try:
            out.append(await get_artifact(workspace_id, a_id))
        except Exception:
            # best-effort: skip missing/broken ids
            pass
    return out


# ─────────────────────────────────────────────────────────────
# Run deltas (OPTIONAL; if you later add an endpoint server-side)
# ─────────────────────────────────────────────────────────────
async def get_run_deltas(
    workspace_id: str,
    run_id: str,
    *,
    include_ids: bool = False,
) -> Dict[str, Any]:
    """
    Optional convenience wrapper if artifact-service exposes:
      GET /artifact/{workspace_id}/deltas?run_id=...&include_ids=true|false
    Not used by discovery flow (we compute diffs here), but kept for compatibility.
    """
    headers = _corr_headers()
    qs = f"?run_id={run_id}&include_ids={'true' if include_ids else 'false'}"
    url = f"{settings.ARTIFACT_SERVICE_URL}/artifact/{workspace_id}/deltas{qs}"
    async with httpx.AsyncClient(timeout=settings.REQUEST_TIMEOUT_S, headers=headers) as client:
        r = await client.get(url)
        if r.is_error:
            raise httpx.HTTPStatusError(f"{r.status_code}: {r.text}", request=r.request, response=r)
        return r.json()
    

# ─────────────────────────────────────────────────────────────
# Kind prompts (optional, used by GenericKindAgent)
# ─────────────────────────────────────────────────────────────
async def get_kind_prompt(kind: str) -> str:
    """
    Fetches the discovery prompt template for a given kind from artifact-service.
    Returns "" if not found.
    """
    headers = _corr_headers()
    base = settings.ARTIFACT_SERVICE_URL.rstrip("/")
    # Endpoint name aligns with our artifact-service routers; tolerate both shapes
    candidates = [
        f"{base}/registry/kinds/{kind}/prompt",
        f"{base}/registry/kind/{kind}/prompt",
    ]
    async with httpx.AsyncClient(timeout=settings.REQUEST_TIMEOUT_S, headers=headers) as client:
        for url in candidates:
            try:
                r = await client.get(url)
                if r.status_code == 404:
                    continue
                r.raise_for_status()
                # Accept either {"prompt": "..."} or raw text
                try:
                    js = r.json()
                    if isinstance(js, dict) and "prompt" in js and isinstance(js["prompt"], str):
                        return js["prompt"]
                except Exception:
                    pass
                return r.text or ""
            except Exception:
                continue
    return ""

