from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime

# ─────────────────────────────────────────────────────────────
# Global Capability (authoritative registry)
# ─────────────────────────────────────────────────────────────
class GlobalCapability(BaseModel):
    id: str = Field(..., description="Stable capability id (e.g., cap.catalog.services)")
    name: str
    description: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    parameters_schema: Optional[Dict[str, Any]] = None
    produces_kinds: List[str] = Field(default_factory=list)  # must be valid kinds
    agent: Optional[str] = None  # e.g., "catalog.services.v1"

class GlobalCapabilityCreate(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    parameters_schema: Optional[Dict[str, Any]] = None
    produces_kinds: List[str] = Field(default_factory=list)
    agent: Optional[str] = None

class GlobalCapabilityUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[List[str]] = None
    parameters_schema: Optional[Dict[str, Any]] = None
    produces_kinds: Optional[List[str]] = None
    agent: Optional[str] = None

# ─────────────────────────────────────────────────────────────
# Pack models
# Denormalized snapshot of capabilities + references
# IMPORTANT: We do NOT enforce "non-empty playbooks/capability_ids" in the
# model itself to keep reads robust. Writes validate in the router.
# ─────────────────────────────────────────────────────────────
class PlaybookStep(BaseModel):
    id: str = Field(..., description="Stable step id (uuid or semantic id)")
    name: str
    capability_id: str = Field(..., description="Global capability id this step invokes")
    description: Optional[str] = None
    params: Dict[str, Any] = Field(default_factory=dict)

class Playbook(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    steps: List[PlaybookStep] = Field(default_factory=list)

class CapabilitySnapshot(BaseModel):
    # snapshot of GlobalCapability at time of pack (for reproducibility)
    id: str
    name: str
    description: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    parameters_schema: Optional[Dict[str, Any]] = None
    produces_kinds: List[str] = Field(default_factory=list)
    agent: Optional[str] = None

class CapabilityPack(BaseModel):
    id: str = Field(..., alias="_id")
    key: str
    version: str
    title: str
    description: str  # required
    capability_ids: List[str] = Field(default_factory=list, description="Refs to global capabilities used")
    capabilities: List[CapabilitySnapshot] = Field(default_factory=list, description="Denormalized snapshots")
    playbooks: List[Playbook] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

class CapabilityPackCreate(BaseModel):
    key: str
    version: str
    title: str
    description: str  # required
    capability_ids: List[str] = Field(default_factory=list)
    playbooks: List[Playbook] = Field(default_factory=list)

class CapabilityPackUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    capability_ids: Optional[List[str]] = None
    playbooks: Optional[List[Playbook]] = None
