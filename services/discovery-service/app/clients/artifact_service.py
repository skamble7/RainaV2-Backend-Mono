#services/discovery-service/app/clients/artifact_service.py
from __future__ import annotations

import os
import asyncio
from typing import Any, Dict, List, Optional

import httpx

# Base URL for artifact-service
ARTIFACT_SVC_URL = os.getenv("ARTIFACT_SERVICE_URL", "http://artifact-service:8011")

# ---- HTTP helpers --------------------------------------------------------
async def _aget(url: str, params: Optional[Dict[str, Any]] = None) -> httpx.Response:
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.get(url, params=params)
        r.raise_for_status()
        return r

async def _apost(
    url: str,
    json_body: Any,
    headers: Optional[Dict[str, str]] = None,
    params: Optional[Dict[str, Any]] = None,
) -> httpx.Response:
    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.post(url, json=json_body, headers=headers or {}, params=params)
        r.raise_for_status()
        return r

async def _apatch(
    url: str,
    json_body: Any,
    headers: Optional[Dict[str, str]] = None,
    params: Optional[Dict[str, Any]] = None,
) -> httpx.Response:
    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.patch(url, json=json_body, headers=headers or {}, params=params)
        r.raise_for_status()
        return r

# ---- Registry lookups ----------------------------------------------------
async def get_kind_doc(kind: str) -> Optional[Dict[str, Any]]:
    """
    Fetch the full kind registry doc (latest schema + prompt).
    """
    url = f"{ARTIFACT_SVC_URL}/registry/kinds/{kind}"
    try:
        resp = await _aget(url)
        return resp.json()
    except httpx.HTTPStatusError:
        return None

async def get_kind_prompt(kind: str) -> Optional[str]:
    """
    Legacy helper: returns the combined prompt string if the endpoint exists.
    """
    url = f"{ARTIFACT_SVC_URL}/registry/kinds/{kind}/prompt"
    try:
        resp = await _aget(url)
        data = resp.json()
        if isinstance(data, dict):
            sys = data.get("system") or ""
            user_tmpl = data.get("user_template") or ""
            return (sys + "\n" + user_tmpl).strip()
        if isinstance(data, str):
            return data
    except httpx.HTTPStatusError:
        pass
    return None

async def get_kind_prompt_and_schema(kind: str) -> Dict[str, Any]:
    """
    Preferred helper: returns {"system","user_template","json_schema","version"}.
    Falls back gracefully if only a prompt endpoint exists.
    """
    doc = await get_kind_doc(kind)
    if doc and isinstance(doc, dict):
        latest = str(doc.get("latest_schema_version") or "")
        svs: List[Dict[str, Any]] = doc.get("schema_versions") or []
        entry: Optional[Dict[str, Any]] = None
        for e in svs:
            if str(e.get("version") or "") == latest:
                entry = e
                break
        entry = entry or (svs[0] if svs else None)
        if entry:
            prompt = entry.get("prompt") or {}
            return {
                "system": prompt.get("system"),
                "user_template": prompt.get("user_template"),
                "json_schema": entry.get("json_schema"),
                "version": entry.get("version"),
            }

    # Fallback to prompt-only endpoint
    prompt_text = await get_kind_prompt(kind)
    return {"system": prompt_text or "", "user_template": None, "json_schema": None, "version": None}

# ---- Artifact reads ------------------------------------------------------
async def get_workspace_with_artifacts(workspace_id: str, include_deleted: bool = False) -> Dict[str, Any]:
    url = f"{ARTIFACT_SVC_URL}/artifact/{workspace_id}/parent"
    params = {"include_deleted": "true"} if include_deleted else None
    resp = await _aget(url, params=params)
    return resp.json()

# Back-compat alias: some callers import get_workspace_parent
async def get_workspace_parent(workspace_id: str, include_deleted: bool = False) -> Dict[str, Any]:
    return await get_workspace_with_artifacts(workspace_id, include_deleted)

async def get_run_deltas(workspace_id: str, run_id: str, include_ids: bool = False) -> Dict[str, Any]:
    url = f"{ARTIFACT_SVC_URL}/artifact/{workspace_id}/deltas"
    params = {"run_id": run_id}
    if include_ids:
        params["include_ids"] = "true"
    resp = await _aget(url, params=params)
    return resp.json()

async def get_artifact(workspace_id: str, artifact_id: str) -> Dict[str, Any]:
    """
    Mirrors GET /artifact/{workspace_id}/{artifact_id}
    """
    url = f"{ARTIFACT_SVC_URL}/artifact/{workspace_id}/{artifact_id}"
    resp = await _aget(url)
    return resp.json()

async def get_artifacts_by_ids(workspace_id: str, artifact_ids: List[str]) -> List[Dict[str, Any]]:
    """
    Convenience helper: fetch multiple artifacts by id.
    Uses concurrent GETs to /artifact/{workspace_id}/{artifact_id}.
    """
    if not artifact_ids:
        return []

    async with httpx.AsyncClient(timeout=30.0) as client:
        async def _fetch(aid: str) -> Optional[Dict[str, Any]]:
            try:
                r = await client.get(f"{ARTIFACT_SVC_URL}/artifact/{workspace_id}/{aid}")
                r.raise_for_status()
                return r.json()
            except httpx.HTTPStatusError:
                return None

        results = await asyncio.gather(*(_fetch(a) for a in artifact_ids))
        return [r for r in results if isinstance(r, dict)]

async def list_artifacts(
    workspace_id: str,
    *,
    kind: Optional[str] = None,
    name_prefix: Optional[str] = None,
    include_deleted: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    """
    Mirrors GET /artifact/{workspace_id} list endpoint.
    """
    url = f"{ARTIFACT_SVC_URL}/artifact/{workspace_id}"
    params: Dict[str, Any] = {
        "include_deleted": "true" if include_deleted else "false",
        "limit": limit,
        "offset": offset,
    }
    if kind:
        params["kind"] = kind
    if name_prefix:
        params["name_prefix"] = name_prefix
    resp = await _aget(url, params=params)
    return resp.json()

# ---- Artifact upserts ----------------------------------------------------
async def upsert_batch(workspace_id: str, items: List[Dict[str, Any]], run_id: Optional[str] = None) -> Dict[str, Any]:
    url = f"{ARTIFACT_SVC_URL}/artifact/{workspace_id}/upsert-batch"
    headers = {"X-Run-Id": run_id} if run_id else {}
    resp = await _apost(url, {"items": items}, headers=headers)
    return resp.json()

async def upsert_single(workspace_id: str, item: Dict[str, Any], run_id: Optional[str] = None) -> Dict[str, Any]:
    url = f"{ARTIFACT_SVC_URL}/artifact/{workspace_id}"
    headers = {"X-Run-Id": run_id} if run_id else {}
    resp = await _apost(url, item, headers=headers)
    return resp.json()

# ---- Baseline inputs -----------------------------------------------------
async def set_inputs_baseline(
    workspace_id: str,
    *,
    avc: Dict[str, Any],
    fss: Dict[str, Any],
    pss: Dict[str, Any],
    if_absent_only: bool = False,
    expected_version: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Mirrors POST /artifact/{workspace_id}/baseline-inputs in artifact-service.
    """
    url = f"{ARTIFACT_SVC_URL}/artifact/{workspace_id}/baseline-inputs"
    params: Dict[str, Any] = {}
    if if_absent_only:
        params["if_absent_only"] = "true"
    if expected_version is not None:
        params["expected_version"] = expected_version

    payload = {"avc": avc, "fss": fss, "pss": pss}
    resp = await _apost(url, payload, params=params)
    return resp.json()

async def patch_inputs_baseline(
    workspace_id: str,
    *,
    avc: Optional[Dict[str, Any]] = None,
    pss: Optional[Dict[str, Any]] = None,
    fss_stories_upsert: Optional[List[Dict[str, Any]]] = None,
    expected_version: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Mirrors PATCH /artifact/{workspace_id}/baseline-inputs in artifact-service.
    """
    url = f"{ARTIFACT_SVC_URL}/artifact/{workspace_id}/baseline-inputs"
    params: Dict[str, Any] = {}
    if expected_version is not None:
        params["expected_version"] = expected_version

    body: Dict[str, Any] = {}
    if avc is not None:
        body["avc"] = avc
    if pss is not None:
        body["pss"] = pss
    if fss_stories_upsert is not None:
        body["fss_stories_upsert"] = fss_stories_upsert

    resp = await _apatch(url, body, params=params)
    return resp.json()
