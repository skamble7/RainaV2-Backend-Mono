# app/db/discovery_runs.py
from datetime import datetime
from typing import Optional, List

from pydantic import UUID4
from pymongo import ASCENDING, DESCENDING
from pymongo.errors import DuplicateKeyError

from app.models.discovery import DiscoveryRun, StartDiscoveryRequest, InputsDiff


COLLECTION = "discovery_runs"


def init_indexes(db):
    col = db[COLLECTION]
    # Many runs per workspace – remove uniqueness
    col.create_index([("workspace_id", ASCENDING), ("created_at", DESCENDING)])
    # Unique id per run
    col.create_index([("run_id", ASCENDING)], unique=True)
    # Useful filters
    col.create_index([("playbook_id", ASCENDING)])
    col.create_index([("status", ASCENDING)])


def create_discovery_run(
    db,
    req: StartDiscoveryRequest,
    run_id: UUID4,
    *,
    input_fingerprint: Optional[str] = None,
    input_diff: Optional[InputsDiff] = None,
    strategy: str = "delta",
) -> DiscoveryRun:
    """Insert a new run in 'created' state (multiple runs per workspace allowed)."""
    col = db[COLLECTION]
    run = DiscoveryRun(
        run_id=run_id,
        workspace_id=req.workspace_id,
        playbook_id=req.playbook_id,
        inputs=req.inputs,
        options=req.options or {},
        input_fingerprint=input_fingerprint,
        input_diff=input_diff,
        strategy=strategy,  # baseline|delta|rebuild
        status="created",
    )
    col.insert_one(run.model_dump(mode="json"))
    return run


def get_by_run_id(db, run_id: UUID4) -> Optional[DiscoveryRun]:
    doc = db[COLLECTION].find_one({"run_id": str(run_id)})
    return DiscoveryRun.model_validate(doc) if doc else None


def list_by_workspace(db, workspace_id: UUID4, limit: int = 50, offset: int = 0) -> List[DiscoveryRun]:
    cur = (
        db[COLLECTION]
        .find({"workspace_id": str(workspace_id)})
        .sort("created_at", DESCENDING)
        .skip(offset)
        .limit(min(limit, 200))
    )
    return [DiscoveryRun.model_validate(d) for d in cur]


def get_latest_by_workspace(db, workspace_id: UUID4) -> Optional[DiscoveryRun]:
    doc = (
        db[COLLECTION]
        .find({"workspace_id": str(workspace_id)})
        .sort("created_at", DESCENDING)
        .limit(1)
        .next(None)
    )
    return DiscoveryRun.model_validate(doc) if doc else None


def delete_by_run_id(db, run_id: UUID4) -> bool:
    res = db[COLLECTION].delete_one({"run_id": str(run_id)})
    return res.deleted_count > 0


def set_status(db, run_id: UUID4, status: str, **fields):
    db[COLLECTION].update_one(
        {"run_id": str(run_id)},
        {"$set": {"status": status, "updated_at": datetime.utcnow(), **fields}},
    )
