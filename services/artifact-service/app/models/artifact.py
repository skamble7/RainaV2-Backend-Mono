# app/models/artifact.py
from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Literal, Optional, List, Any, Dict
from datetime import datetime
from uuid import uuid4

# ---- Types ----
ArtifactKind = Literal[
    "cam.document", "cam.context_map", "cam.capability_model", "cam.service_contract",
    "cam.sequence_diagram", "cam.erd", "cam.adr_index"
]

class Provenance(BaseModel):
    author: Optional[str] = None
    agent: Optional[str] = None
    capability_pack: Optional[str] = None
    reason: Optional[str] = None

# Snapshot of the workspace as known to artifacts-service.
# We keep it flexible so we can copy whatever workspace-service sends.
class WorkspaceSnapshot(BaseModel):
    id: str = Field(..., alias="_id")        # workspace id from workspace-service
    name: str
    description: Optional[str] = None
    created_by: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        allow_population_by_field_name = True
        extra = "allow"  # accept additional fields without validation errors

# Embedded artifact item living inside the workspace document
class ArtifactItem(BaseModel):
    artifact_id: str = Field(default_factory=lambda: str(uuid4()))
    kind: ArtifactKind
    name: str
    data: Dict[str, Any]
    version: int = 1
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    deleted_at: Optional[datetime] = None
    provenance: Optional[Provenance] = None

# Payloads for write operations
class ArtifactItemCreate(BaseModel):
    kind: ArtifactKind
    name: str
    data: Dict[str, Any]
    provenance: Optional[Provenance] = None

class ArtifactItemReplace(BaseModel):
    data: Dict[str, Any]
    provenance: Optional[Provenance] = None

class ArtifactItemPatchIn(BaseModel):
    patch: List[Dict[str, Any]]  # JSON Patch ops
    provenance: Optional[Provenance] = None

# The single MongoDB document per workspace that aggregates artifacts
class WorkspaceArtifactsDoc(BaseModel):
    id: str = Field(..., alias="_id")        # Mongo _id for this doc
    workspace_id: str                        # convenience for querying
    workspace: WorkspaceSnapshot             # denormalized snapshot of workspace
    artifacts: List[ArtifactItem] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        allow_population_by_field_name = True
