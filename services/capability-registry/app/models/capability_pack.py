from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime

class Capability(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    # tags (for discovery routing), inputs/outputs schemas later
    tags: List[str] = []
    parameters_schema: Optional[Dict[str, Any]] = None
    produces_kinds: List[str] = []  # e.g., ["cam.service_contract"]

class Playbook(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    steps: List[Dict[str, Any]] = []  # ordered capability refs + params

class CapabilityPack(BaseModel):
    id: str = Field(..., alias="_id")
    key: str  # e.g., "svc-micro"
    version: str  # e.g., "v1"
    title: str
    description: Optional[str] = None
    capabilities: List[Capability] = []
    playbooks: List[Playbook] = []
    created_at: datetime
    updated_at: datetime

class CapabilityPackCreate(BaseModel):
    key: str
    version: str
    title: str
    description: Optional[str] = None
    capabilities: List[Capability] = []
    playbooks: List[Playbook] = []

class CapabilityPackUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    capabilities: Optional[List[Capability]] = None
    playbooks: Optional[List[Playbook]] = None
