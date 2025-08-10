from pydantic import BaseModel, Field
from typing import Literal, Optional
from datetime import datetime

ArtifactKind = Literal[
    "cam.document","cam.context_map","cam.capability_model","cam.service_contract",
    "cam.sequence_diagram","cam.erd","cam.adr_index"
]

class Provenance(BaseModel):
    author: Optional[str] = None
    agent: Optional[str] = None
    capability_pack: Optional[str] = None
    reason: Optional[str] = None

class Artifact(BaseModel):
    id: str = Field(..., alias="_id")
    workspace_id: str
    kind: ArtifactKind
    name: str
    data: dict
    version: int
    created_at: datetime
    updated_at: datetime
    deleted_at: Optional[datetime] = None
    provenance: Optional[Provenance] = None

class ArtifactCreate(BaseModel):
    kind: ArtifactKind
    name: str
    data: dict
    provenance: Optional[Provenance] = None

class ArtifactReplace(BaseModel):
    data: dict
    provenance: Optional[Provenance] = None

class ArtifactPatchIn(BaseModel):
    patch: list[dict]
    provenance: Optional[Provenance] = None
