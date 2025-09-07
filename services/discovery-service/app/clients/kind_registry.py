from __future__ import annotations

import json
import uuid
from typing import Any, Dict, Optional, Tuple

import httpx

from app.config import settings

# Pull IDs from middleware if present (falls back to fresh UUIDs)
try:
    from app.middleware.correlation import request_id_var, correlation_id_var  # type: ignore
except Exception:  # pragma: no cover
    request_id_var = correlation_id_var = None  # type: ignore

def _corr_headers(extra: Optional[dict] = None) -> dict:
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
    base = {"x-request-id": rid, "x-correlation-id": cid}
    if extra:
        base.update(extra)
    return base


# Simple in-memory cache with ETag invalidation
_CACHE: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
_REGISTRY_ETAG: Optional[str] = None


async def _refresh_etag(client: httpx.AsyncClient) -> Optional[str]:
    global _REGISTRY_ETAG
    r = await client.get(f"{settings.ARTIFACT_SERVICE_URL}/registry/meta")
    if r.status_code == 404:
        return _REGISTRY_ETAG
    r.raise_for_status()
    meta = r.json() or {}
    etag = meta.get("etag")
    if etag and etag != _REGISTRY_ETAG:
        _CACHE.clear()
        _REGISTRY_ETAG = etag
    return _REGISTRY_ETAG


def _selectors_key(selectors: Optional[Dict[str, Any]]) -> str:
    if not selectors:
        return ""
    try:
        return json.dumps(selectors, sort_keys=True, separators=(",", ":"))
    except Exception:
        return str(selectors)


def _default_kind_doc(kind: str) -> Dict[str, Any]:
    return {
        "kind": kind,
        "latest_schema_version": "1.0.0",
        "schema": {"type": "object", "additionalProperties": True},
        "prompt": {
            "system": "You are RAINA. Produce exactly one JSON object that matches the provided schema (fields you don't know may be omitted).",
            "user_template": None,
            "strict_json": True,
        },
        "identity": {"natural_key": ["name"], "summary_rule": "{{name}}"},
        "aliases": [],
        "category": None,
        "title": kind.split(".")[-1],
    }


async def get_kind(kind: str, *, selectors: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Fetch a kind definition from artifact-service's registry (with prompt & schema).
    Caches per (kind, version, selectors_json); cache invalidated when registry ETag changes.
    Returns a dict with at least: { "kind", "latest_schema_version", "schema", "prompt", "identity" }.
    """
    headers = _corr_headers()
    async with httpx.AsyncClient(timeout=settings.REQUEST_TIMEOUT_S, headers=headers) as client:
        await _refresh_etag(client)

        params = {}
        if selectors:
            if "paradigm" in selectors:
                params["paradigm"] = selectors["paradigm"]
            if "style" in selectors:
                params["style"] = selectors["style"]

        r = await client.get(f"{settings.ARTIFACT_SERVICE_URL}/registry/kinds/{kind}", params=params)
        if r.status_code == 404:
            # Allow legacy/alias kinds to proceed with a generic shape; artifact-service
            # will canonicalize/validate on write.
            return _default_kind_doc(kind)
        r.raise_for_status()
        doc = r.json() or {}

        latest = doc.get("latest_schema_version") or ""
        versions = doc.get("schema_versions") or []
        entry = None
        if latest:
            entry = next((v for v in versions if v.get("version") == latest), None)
        if entry is None and versions:
            entry = versions[-1]

        if not entry:
            return _default_kind_doc(kind)

        key = (kind, str(entry.get("version")), _selectors_key(selectors))
        if key in _CACHE:
            return _CACHE[key]

        out = {
            "kind": doc.get("_id") or kind,
            "latest_schema_version": str(entry.get("version") or doc.get("latest_schema_version") or "1.0.0"),
            "schema": entry.get("json_schema") or {"type": "object", "additionalProperties": True},
            "prompt": entry.get("prompt") or _default_kind_doc(kind)["prompt"],
            "identity": entry.get("identity") or {"natural_key": ["name"], "summary_rule": "{{name}}"},
            "aliases": doc.get("aliases") or [],
            "category": doc.get("category"),
            "title": doc.get("title"),
        }
        _CACHE[key] = out
        return out
