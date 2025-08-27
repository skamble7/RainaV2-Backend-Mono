# services/discovery-service/app/main.py

from __future__ import annotations

import json
import logging
import httpx
import asyncio
import pymongo
from uuid import uuid4
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List, Tuple

from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends, Query
from fastapi.responses import ORJSONResponse
from pydantic import UUID4

from app.config import settings
from app.logging import setup_logging
from app.models.discovery import (
    StartDiscoveryRequest,
    DiscoveryRun,
    InputsDiff,
    ArtifactsDiff,
    RunDeltas,
)
from app.models.state import DiscoveryState
from app.graphs.discovery_graph import build_graph
from app.infra.rabbit import publish_event_v1

from app.db.discovery_runs import (
    init_indexes,
    create_discovery_run,
    get_by_run_id,
    list_by_workspace,
    delete_by_run_id,
    set_status,
)

# artifact-service helpers
from app.clients.artifact_service import (
    set_inputs_baseline,
    get_workspace_parent,
    get_artifact,
    get_artifacts_by_ids,
)

# --- Correlation middleware & logging filter ----------------------------
from app.middleware.correlation import (
    CorrelationIdMiddleware,
    CorrelationIdFilter,
    request_id_var,
    correlation_id_var,
)

_RESERVED = {
    "name","msg","args","levelname","levelno","pathname","filename","module",
    "exc_info","exc_text","stack_info","lineno","funcName","created","msecs",
    "relativeCreated","thread","threadName","process","processName","message","asctime"
}
def safe_extra(extra: dict) -> dict:
    out = {}
    for k, v in extra.items():
        out[f"ctx_{k}" if k in _RESERVED else k] = v
    return out

logger = setup_logging()
app = FastAPI(default_response_class=ORJSONResponse, title=settings.SERVICE_NAME)
app.add_middleware(CorrelationIdMiddleware)
_corr_filter = CorrelationIdFilter()
for _n in ("", "uvicorn", "uvicorn.access", "uvicorn.error", "app"):
    logging.getLogger(_n).addFilter(_corr_filter)

def _corr_headers() -> dict:
    hdrs = {}
    try:
        rid = request_id_var.get()
        cid = correlation_id_var.get()
        if rid: hdrs["x-request-id"] = rid
        if cid: hdrs["x-correlation-id"] = cid
    except Exception:
        pass
    return hdrs

# ---- DB wiring ----------------------------------------------------------
def get_db():
    client = pymongo.MongoClient(settings.MONGO_URI, tz_aware=True)
    return client[settings.MONGO_DB]

@app.on_event("startup")
def _startup():
    db = get_db()
    init_indexes(db)
    logger.info("Indexes initialized for discovery_runs", extra=safe_extra({"service": settings.SERVICE_NAME}))

# ---- health -------------------------------------------------------------
@app.get("/health")
async def health():
    return {"ok": True, "service": settings.SERVICE_NAME, "env": settings.ENV}

@app.get("/ready")
async def ready():
    try:
        async with httpx.AsyncClient(timeout=settings.REQUEST_TIMEOUT_S, headers=_corr_headers()) as client:
            await client.get(f"{settings.CAPABILITY_REGISTRY_URL}/health")
            await client.get(f"{settings.ARTIFACT_SERVICE_URL}/health")
    except Exception as e:
        raise HTTPException(503, f"Not ready: {e}")
    return {"ready": True}

# ---- inputs fingerprint & diff -----------------------------------------
def _canonical(obj: Dict[str, Any]) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))

def _sha256(s: str) -> str:
    import hashlib
    return hashlib.sha256(s.encode("utf-8")).hexdigest()

def _list_diff(old: List[str], new: List[str]) -> Dict[str, List[str]]:
    old_s, new_s = set(old), set(new)
    return {"added": sorted(list(new_s - old_s)), "removed": sorted(list(old_s - new_s))}

def _inputs_diff(baseline: Dict[str, Any], candidate: Dict[str, Any]) -> InputsDiff:
    from app.models.discovery import InputsDiff, AVCDiff, FSSDiff, PSSDiff

    b = baseline or {}
    c = candidate or {}

    # --- AVC
    b_goals = {g["id"]: g for g in b.get("avc", {}).get("goals", [])}
    c_goals = {g["id"]: g for g in c.get("avc", {}).get("goals", [])}
    added_goals = sorted([k for k in c_goals.keys() - b_goals.keys()])
    removed_goals = sorted([k for k in b_goals.keys() - c_goals.keys()])
    updated_goals = []
    for gid in (c_goals.keys() & b_goals.keys()):
        changed = []
        for fld in ("text", "metric"):
            if (c_goals[gid].get(fld) != b_goals[gid].get(fld)):
                changed.append(fld)
        if changed:
            updated_goals.append({"id": gid, "fields": changed})

    avc_diff = AVCDiff(
        added_goals=added_goals,
        removed_goals=removed_goals,
        updated_goals=updated_goals,
        added_vision=_list_diff(b.get("avc", {}).get("vision", []), c.get("avc", {}).get("vision", []))["added"],
        removed_vision=_list_diff(b.get("avc", {}).get("vision", []), c.get("avc", {}).get("vision", []))["removed"],
        added_nfrs=_list_diff([n.get("type") for n in b.get("avc", {}).get("non_functionals", [])],
                              [n.get("type") for n in c.get("avc", {}).get("non_functionals", [])])["added"],
        removed_nfrs=_list_diff([n.get("type") for n in b.get("avc", {}).get("non_functionals", [])],
                                [n.get("type") for n in c.get("avc", {}).get("non_functionals", [])])["removed"],
    )

    # --- FSS
    b_stories = {s["key"]: s for s in b.get("fss", {}).get("stories", [])}
    c_stories = {s["key"]: s for s in c.get("fss", {}).get("stories", [])}
    added_keys = sorted(list(c_stories.keys() - b_stories.keys()))
    removed_keys = sorted(list(b_stories.keys() - c_stories.keys()))
    updated = []
    for key in (c_stories.keys() & b_stories.keys()):
        changed = []
        for fld in ("title", "description", "acceptance_criteria", "tags"):
            if c_stories[key].get(fld) != b_stories[key].get(fld):
                changed.append(fld)
        if changed:
            updated.append({"key": key, "fields": changed})
    fss_diff = FSSDiff(added_keys=added_keys, removed_keys=removed_keys, updated=updated)

    # --- PSS
    b_pss = b.get("pss", {}) or {}
    c_pss = c.get("pss", {}) or {}
    pss_diff = PSSDiff(
        paradigm_changed=(b_pss.get("paradigm") != c_pss.get("paradigm")),
        style_added=_list_diff(b_pss.get("style", []), c_pss.get("style", []))["added"],
        style_removed=_list_diff(b_pss.get("style", []), c_pss.get("style", []))["removed"],
        tech_added=_list_diff(b_pss.get("tech_stack", []), c_pss.get("tech_stack", []))["added"],
        tech_removed=_list_diff(b_pss.get("tech_stack", []), c_pss.get("tech_stack", []))["removed"],
    )

    return InputsDiff(avc=avc_diff, fss=fss_diff, pss=pss_diff)

async def _fetch_workspace_baseline_inputs(workspace_id: str) -> Dict[str, Any]:
    async with httpx.AsyncClient(timeout=settings.REQUEST_TIMEOUT_S, headers=_corr_headers()) as client:
        r = await client.get(f"{settings.ARTIFACT_SERVICE_URL}/artifact/{workspace_id}/parent")
        if r.status_code == 404:
            return {}
        r.raise_for_status()
        parent = r.json()
        return parent.get("inputs_baseline") or {}

# ─────────────────────────────────────────────────────────────
# Artifact diffing helpers
# ─────────────────────────────────────────────────────────────
def _nk(a: Dict[str, Any]) -> str:
    return (a.get("natural_key") or f"{a.get('kind')}:{a.get('name')}").lower()

def _counts(diff: ArtifactsDiff) -> Dict[str, int]:
    return {
        "new": len(diff.new),
        "updated": len(diff.updated),
        "unchanged": len(diff.unchanged),
        "retired": len(diff.retired),
        "deleted": 0,  # reserved for future hard-deletes
    }

def _select_baseline_run_id(db, workspace_id: str, fallback_exclude: Optional[str] = None) -> Optional[str]:
    """
    Strategy:
      1) If artifact-service parent says last_promoted_run_id -> use it
      2) Else earliest completed 'baseline' run
      3) Else earliest completed run (excluding current if provided)
    """
    try:
        # Best-effort call to artifact-service for last_promoted_run_id
        parent = asyncio.get_event_loop().run_until_complete(get_workspace_parent(workspace_id))
        lp = parent.get("last_promoted_run_id")
        if lp:
            return str(lp)
    except Exception:
        pass

    coll = db["discovery_runs"]
    # 2) earliest completed baseline
    doc = coll.find_one(
        {"workspace_id": workspace_id, "status": "completed", "strategy": "baseline"},
        sort=[("created_at", 1)],
        projection={"run_id": 1},
    )
    if doc and doc.get("run_id"):
        rid = str(doc["run_id"])
        if fallback_exclude and rid == fallback_exclude:
            doc = None
        else:
            return rid

    # 3) earliest completed (not the current run)
    filt = {"workspace_id": workspace_id, "status": "completed"}
    if fallback_exclude:
        filt["run_id"] = {"$ne": fallback_exclude}
    doc = coll.find_one(filt, sort=[("created_at", 1)], projection={"run_id": 1})
    return str(doc["run_id"]) if doc and doc.get("run_id") else None

async def _compute_artifacts_diff_for_run(db, workspace_id: str, run_id: str, run_summary: Dict[str, Any]) -> ArtifactsDiff:
    """
    Compute diff between this run (right) and the chosen baseline run (left).
    Returns and also persists into the run document.
    """
    # Figure out baseline run to compare with
    base_run_id = _select_baseline_run_id(db, workspace_id, fallback_exclude=run_id)

    # Collect artifact ids for right (current) and left (baseline)
    right_ids: List[str] = run_summary.get("artifact_ids", []) or []

    left_ids: List[str] = []
    if base_run_id:
        base = get_by_run_id(db, UUID4(base_run_id))
        if base and base.result_summary:
            left_ids = base.result_summary.get("artifact_ids", []) or []

    # Edge case: no baseline → everything new
    if not left_ids:
        right_docs = await get_artifacts_by_ids(workspace_id, right_ids)
        diff = ArtifactsDiff(
            new=sorted({_nk(a) for a in right_docs}),
            updated=[],
            unchanged=[],
            retired=[],
        )
        diff.counts = _counts(diff)
        return diff

    # Fetch both sides from artifact-service
    left_docs = await get_artifacts_by_ids(workspace_id, left_ids)
    right_docs = await get_artifacts_by_ids(workspace_id, right_ids)

    L = { _nk(a): a for a in left_docs }
    R = { _nk(a): a for a in right_docs }

    new_keys: List[str] = []
    upd_keys: List[str] = []
    same_keys: List[str] = []
    ret_keys: List[str] = []

    # New / Updated / Unchanged
    for nk, r in R.items():
        l = L.get(nk)
        if not l:
            new_keys.append(nk)
        else:
            # If artifact_id/fingerprint differs -> updated, else unchanged
            lid = str(l.get("artifact_id") or "")
            rid = str(r.get("artifact_id") or "")
            lfp = l.get("fingerprint")
            rfp = r.get("fingerprint")
            if (lid and rid and lid == rid) or (lfp and rfp and lfp == rfp):
                same_keys.append(nk)
            else:
                upd_keys.append(nk)

    # Retired
    for nk in L.keys():
        if nk not in R:
            ret_keys.append(nk)

    diff = ArtifactsDiff(
        new=sorted(new_keys),
        updated=sorted(upd_keys),
        unchanged=sorted(same_keys),
        retired=sorted(ret_keys),
    )
    diff.counts = _counts(diff)
    return diff

async def _persist_run_diff(db, run_id: UUID4, diff: ArtifactsDiff) -> None:
    coll = db["discovery_runs"]
    coll.update_one(
        {"run_id": str(run_id)},
        {
            "$set": {
                "artifacts_diff": diff.model_dump(mode="json"),
                "deltas": RunDeltas(counts=diff.counts).model_dump(mode="json"),
                "updated_at": datetime.utcnow(),
            }
        },
    )

# ---- background worker -------------------------------------------------
async def _run_discovery(req: StartDiscoveryRequest, run_id: UUID4):
    start_ts = datetime.now(timezone.utc)
    db = get_db()
    run_graph = build_graph()
    model_id = (req.options.model if req.options else None) or settings.MODEL_ID

    logger.info("discovery.options.received",
        extra=safe_extra({"options": (req.options.model_dump(by_alias=True) if req.options else {})})
    )

    state: DiscoveryState = {
        "workspace_id": str(req.workspace_id),
        "playbook_id": req.playbook_id,
        "model_id": model_id,
        "inputs": req.inputs.model_dump(),
        "options": (req.options.model_dump() if req.options else {}),
        "artifacts": [],
        "logs": [],
        "errors": [],
        "context": {
            "dry_run": bool(req.options and req.options.dry_run),
            "run_id": str(run_id),
        },
    }

    # NEW: Capture initial baseline inputs in artifact-service if absent
    try:
        await set_inputs_baseline(
            workspace_id=str(req.workspace_id),
            inputs=req.inputs.model_dump(),
            run_id=str(run_id),
            if_absent_only=True,     # do not override an existing baseline
        )
    except Exception as e:
        # Non-fatal: log & continue so discovery still runs
        state.setdefault("logs", []).append(f"inputs_baseline capture skipped: {e}")

    try:
        set_status(db, run_id, "running")
    except Exception:
        logger.exception("Failed to set run status to running", extra=safe_extra({"run_id": str(run_id)}))

    # Include title/description in the STARTED event if present
    publish_event_v1(
        org=settings.EVENTS_ORG,
        event="started",
        payload={
            "run_id": str(run_id),
            "workspace_id": str(req.workspace_id),
            "playbook_id": req.playbook_id,
            "model_id": model_id,
            "received_at": start_ts.isoformat(),
            "title": getattr(req, "title", None),
            "description": getattr(req, "description", None),
        },
        headers=_corr_headers(),
    )

    try:
        result = await run_graph.ainvoke(state)
        completed_at = datetime.now(timezone.utc)
        summary = {
            "run_id": str(run_id),
            "workspace_id": str(req.workspace_id),
            "playbook_id": str(req.playbook_id),
            "artifact_ids": result.get("context", {}).get("artifact_ids", []),
            "validations": result.get("validations", []),
            "logs": result.get("logs", []),
            "started_at": start_ts.isoformat(),
            "completed_at": completed_at.isoformat(),
            "duration_s": (completed_at - start_ts).total_seconds(),
            # Echo title/description for consumers that want it later
            "title": getattr(req, "title", None),
            "description": getattr(req, "description", None),
        }

        # First, mark the run completed and store summary
        set_status(db, run_id, "completed", result_summary=summary, result_artifacts_ref=None)

        # Compute & persist artifacts diff (drives delta pills + diff viewer)
        try:
            diff = await _compute_artifacts_diff_for_run(db, str(req.workspace_id), str(run_id), summary)
            await _persist_run_diff(db, run_id, diff)
        except Exception as diff_err:
            logger.exception("artifacts.diff.compute_failed", extra=safe_extra({"run_id": str(run_id), "error": str(diff_err)}))

        publish_event_v1(org=settings.EVENTS_ORG, event="completed", payload=summary, headers=_corr_headers())

    except Exception as e:
        logger.exception("discovery_failed", extra=safe_extra({"run_id": str(run_id)}))
        fail_payload = {
            "run_id": str(run_id),
            "workspace_id": str(req.workspace_id),
            "error": str(e),
            "logs": state.get("logs", []),
            "errors": state.get("errors", []),
            "artifact_failures": state.get("context", {}).get("artifact_failures", []),
            "started_at": start_ts.isoformat(),
            "failed_at": datetime.now(timezone.utc).isoformat(),
            "title": getattr(req, "title", None),
            "description": getattr(req, "description", None),
        }
        try:
            set_status(get_db(), run_id, "failed", error=str(e))
        except Exception:
            logger.exception("Failed to set run status to failed", extra=safe_extra({"run_id": str(run_id)}))

        publish_event_v1(org=settings.EVENTS_ORG, event="failed", payload=fail_payload, headers=_corr_headers())

# ---- endpoints ----------------------------------------------------------
@app.post("/discover/{workspace_id}", status_code=202)
async def discover(workspace_id: str, req: StartDiscoveryRequest, bg: BackgroundTasks, db=Depends(get_db)):
    if str(req.workspace_id) != workspace_id:
        raise HTTPException(status_code=400, detail="workspace_id in path and body must match")

    baseline_inputs = await _fetch_workspace_baseline_inputs(workspace_id)
    candidate_inputs = req.inputs.model_dump()
    input_fingerprint = _sha256(_canonical(candidate_inputs))
    input_diff = _inputs_diff(baseline_inputs, candidate_inputs)

    run_id: UUID4 = UUID4(str(uuid4()))
    _ = create_discovery_run(
        db,
        req,
        run_id,
        input_fingerprint=input_fingerprint,
        input_diff=input_diff,
        strategy="delta",
    )

    bg.add_task(_run_discovery, req, run_id)

    return {
        "accepted": True,
        "run_id": str(run_id),
        "workspace_id": workspace_id,
        "playbook_id": req.playbook_id,
        "model_id": (req.options.model if req.options else None) or settings.MODEL_ID,
        "dry_run": bool(req.options and req.options.dry_run),
        "title": getattr(req, "title", None),
        "description": getattr(req, "description", None),
        "request_id": request_id_var.get(),
        "correlation_id": correlation_id_var.get(),
        "message": "Discovery started; query status with GET /runs/{run_id} or list via GET /runs?workspace_id=...",
    }

# NOTE: We drop response_model enforcement so we can enrich payloads with 'deltas'
@app.get("/runs/{run_id}")
async def get_run(run_id: UUID4, include_ids: bool = Query(default=False), db=Depends(get_db)):
    run = get_by_run_id(db, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Discovery run not found.")
    doc = run.model_dump(mode="json")

    # If diff wasn't persisted (legacy runs), compute on the fly and persist
    try:
        if not doc.get("artifacts_diff") and run.result_summary:
            diff = await _compute_artifacts_diff_for_run(
                db, doc["workspace_id"], doc["run_id"], run.result_summary
            )
            await _persist_run_diff(db, run_id, diff)
            doc["artifacts_diff"] = diff.model_dump(mode="json")
            doc["deltas"] = RunDeltas(counts=diff.counts).model_dump(mode="json")
    except Exception:
        # best-effort enrichment
        pass

    return doc

@app.get("/runs")
async def list_runs(
    workspace_id: UUID4 = Query(...),
    limit: int = 50,
    offset: int = 0,
    include_delta_counts: bool = Query(default=True, description="Attach deltas.counts to each run"),
    db=Depends(get_db),
):
    runs = list_by_workspace(db, workspace_id, limit=limit, offset=offset)
    out: List[Dict[str, Any]] = []
    for r in runs:
        dct = r.model_dump(mode="json")
        if include_delta_counts:
            try:
                if dct.get("deltas", {}).get("counts"):
                    pass
                elif dct.get("artifacts_diff", {}).get("counts"):
                    dct["deltas"] = {"counts": dct["artifacts_diff"]["counts"]}
                elif r.result_summary:
                    diff = await _compute_artifacts_diff_for_run(
                        db, dct["workspace_id"], dct["run_id"], r.result_summary
                    )
                    await _persist_run_diff(db, r.run_id, diff)
                    dct["deltas"] = {"counts": diff.counts}
            except Exception:
                pass
        out.append(dct)
    return out

@app.delete("/runs/{run_id}", status_code=204)
def delete_run(run_id: UUID4, db=Depends(get_db)):
    ok = delete_by_run_id(db, run_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Discovery run not found.")
    return ORJSONResponse(status_code=204, content=None)
