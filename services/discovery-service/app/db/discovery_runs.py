# app/db/discovery_runs.py
from datetime import datetime
from uuid import uuid4
from typing import Optional

from pymongo.errors import DuplicateKeyError
from pydantic import UUID4

from app.models.discovery import DiscoveryRun, StartDiscoveryRequest

COLLECTION = "discovery_runs"


def init_indexes(db):
    col = db[COLLECTION]
    # Enforce one run per workspace (string key)
    col.create_index("workspace_id", unique=True)
    # Correlation id for lookups/updates (string key)
    col.create_index("discovery_run_id", unique=True)
    # Helpful secondary filter
    col.create_index("playbook_id")


def create_discovery_run(db, req: StartDiscoveryRequest, run_id: UUID4) -> DiscoveryRun:
    """
    Insert a new run in 'created' state.
    UUIDs are serialized to strings at the DB boundary to avoid BSON UUID pitfalls.
    """
    col = db[COLLECTION]
    run = DiscoveryRun(
        discovery_run_id=run_id,
        workspace_id=req.workspace_id,
        playbook_id=req.playbook_id,
        inputs=req.inputs,
        options=req.options or {},
        status="created",
    )
    try:
        # Ensure UUIDs are stored as strings
        col.insert_one(run.model_dump(mode="json"))
    except DuplicateKeyError:
        # Unique index on workspace_id enforces one run per workspace
        raise ValueError("A discovery run already exists for this workspace_id.")
    return run


def get_by_workspace(db, workspace_id: UUID4) -> Optional[DiscoveryRun]:
    """
    Fetch run by workspace (UUID accepted; string used for query).
    """
    doc = db[COLLECTION].find_one({"workspace_id": str(workspace_id)})
    return DiscoveryRun.model_validate(doc) if doc else None


def delete_by_workspace(db, workspace_id: UUID4) -> bool:
    """
    Hard delete the run so a new one can be created (one-run-per-workspace policy).
    """
    res = db[COLLECTION].delete_one({"workspace_id": str(workspace_id)})
    return res.deleted_count > 0


def set_status(db, run_id: UUID4, status: str, **fields):
    """
    Update run status and arbitrary fields (e.g., result_summary, error).
    """
    db[COLLECTION].update_one(
        {"discovery_run_id": str(run_id)},
        {"$set": {"status": status, "updated_at": datetime.utcnow(), **fields}},
    )
