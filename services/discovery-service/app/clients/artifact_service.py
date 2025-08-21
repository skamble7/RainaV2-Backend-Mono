# app/clients/artifact_service.py
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
    """
    Versioned upsert of a single artifact.
    Returns the artifact JSON; server sets X-Op header (insert|update|noop).
    """
    headers = _corr_headers({"X-Run-Id": run_id} if run_id else None)
    url = f"{settings.ARTIFACT_SERVICE_URL}/artifact/{workspace_id}"
    async with httpx.AsyncClient(timeout=settings.REQUEST_TIMEOUT_S, headers=headers) as client:
        r = await client.post(url, json=item)
        if r.is_error:
            raise httpx.HTTPStatusError(f"{r.status_code}: {r.text}", request=r.request, response=r)
        return r.json()


async def upsert_batch(workspace_id: str, items: List[Dict[str, Any]], *, run_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Batch versioned upsert.
    Returns:
      {
        "counts": {"insert": n, "update": n, "noop": n, "failed": n},
        "results": [
          {"artifact_id": "...", "natural_key": "...", "op": "insert|update|noop", "version": 1} | {"error": "..."},
          ...
        ]
      }
    """
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
    """
    Backward-compatible helper.
    Uses the single upsert endpoint; ignores idempotency_key (fingerprint handles noops).
    """
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
