# app/models/artifact.py
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, Field, ConfigDict

# ─────────────────────────────────────────────────────────────
# Types
# ─────────────────────────────────────────────────────────────
ArtifactKind = Literal[
    "cam.document",
    "cam.context_map",
    "cam.capability_model",
    "cam.service_contract",
    "cam.sequence_diagram",
    "cam.erd",
    "cam.adr_index",
]

class Provenance(BaseModel):
    """Single, structured provenance record stamped on writes."""
    run_id: Optional[str] = None
    playbook_id: Optional[str] = None
    model_id: Optional[str] = None
    step: Optional[str] = None
    pack_key: Optional[str] = None
    pack_version: Optional[str] = None
    inputs_fingerprint: Optional[str] = None
    author: Optional[str] = None         # free-form (e.g., user)
    agent: Optional[str] = None          # e.g., "svc_discovery"
    reason: Optional[str] = None         # short note

class WorkspaceSnapshot(BaseModel):
    """Denormalized snapshot of the workspace, as known to artifact-service."""
    # allow unknowns & allow aliasing from/to "_id"
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    id: str = Field(..., alias="_id")         # <- use alias for Mongo-style _id
    name: str
    description: Optional[str] = None
    created_by: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

class Lineage(BaseModel):
    first_seen_run_id: Optional[str] = None
    last_seen_run_id: Optional[str] = None
    supersedes: List[str] = Field(default_factory=list)  # prior artifact_ids
    superseded_by: Optional[str] = None

class ArtifactItem(BaseModel):
    """Embedded artifact stored inside the per-workspace parent document."""
    artifact_id: str = Field(default_factory=lambda: str(uuid4()))
    kind: ArtifactKind
    name: str
    data: Dict[str, Any]

    # Identity & versioning
    natural_key: Optional[str] = None          # per-kind deterministic key
    fingerprint: Optional[str] = None          # sha256 over normalized data
    version: int = 1
    lineage: Optional[Lineage] = None

    # Timestamps / status
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    deleted_at: Optional[datetime] = None

    provenance: Optional[Provenance] = None

class ArtifactItemCreate(BaseModel):
    """Write payload used by discovery-service (or UI) to add/upsert artifacts."""
    kind: ArtifactKind
    name: str
    data: Dict[str, Any]
    natural_key: Optional[str] = None
    fingerprint: Optional[str] = None
    provenance: Optional[Provenance] = None

class ArtifactItemReplace(BaseModel):
    data: Dict[str, Any]
    provenance: Optional[Provenance] = None

class ArtifactItemPatchIn(BaseModel):
    patch: List[Dict[str, Any]]               # RFC 6902 JSON Patch
    provenance: Optional[Provenance] = None

class WorkspaceArtifactsDoc(BaseModel):
    """Single MongoDB document per workspace aggregating all artifacts + baseline."""
    _id: str                                   # Mongo _id for this doc
    workspace_id: str                          # convenience for querying
    workspace: WorkspaceSnapshot

    # Baseline inputs (latest approved)
    inputs_baseline: Dict[str, Any] = Field(default_factory=dict)     # { avc, fss, pss }
    inputs_baseline_fingerprint: Optional[str] = None                 # ← NEW: sha256 over canonical(inputs_baseline)
    inputs_baseline_version: int = 1
    last_promoted_run_id: Optional[str] = None

    artifacts: List[ArtifactItem] = Field(default_factory=list)

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
