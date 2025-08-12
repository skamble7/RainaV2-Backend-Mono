# capability_pack.py
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime

class Capability(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    parameters_schema: Optional[Dict[str, Any]] = None
    produces_kinds: List[str] = Field(default_factory=list)  # e.g., ["cam.service_contract"]
    agent: Optional[str] = None  # <-- NEW (e.g., "catalog.services.v1")

class Playbook(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    steps: List[Dict[str, Any]] = Field(default_factory=list)  # ordered capability refs + params

class CapabilityPack(BaseModel):
    id: str = Field(..., alias="_id")
    key: str
    version: str
    title: str
    description: Optional[str] = None
    capabilities: List[Capability] = Field(default_factory=list)
    playbooks: List[Playbook] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

class CapabilityPackCreate(BaseModel):
    key: str
    version: str
    title: str
    description: Optional[str] = None
    capabilities: List[Capability] = Field(default_factory=list)
    playbooks: List[Playbook] = Field(default_factory=list)

class CapabilityPackUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    capabilities: Optional[List[Capability]] = None
    playbooks: Optional[List[Playbook]] = None
