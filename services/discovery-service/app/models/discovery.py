# app/models/discovery.py
from __future__ import annotations
from typing import List, Dict, Optional, Any
from pydantic import BaseModel, Field, UUID4
from datetime import datetime

# ---------- AVC ----------
class AVCGoal(BaseModel):
    id: str
    text: str
    metric: Optional[str] = None

class AVCNonFunctional(BaseModel):
    type: str
    target: str

class AVCContext(BaseModel):
    domain: Optional[str] = None
    actors: List[str] = []

class AVCSuccessCriterion(BaseModel):
    kpi: str
    target: str

class AVC(BaseModel):
    vision: List[str] = []
    problem_statements: List[str] = []
    goals: List[AVCGoal] = []
    non_functionals: List[AVCNonFunctional] = []
    constraints: List[str] = []
    assumptions: List[str] = []
    context: AVCContext = Field(default_factory=AVCContext)
    success_criteria: List[AVCSuccessCriterion] = []

# ---------- FSS ----------
class FSSStory(BaseModel):
    key: str
    title: str
    description: str
    acceptance_criteria: List[str] = []
    tags: List[str] = []  # e.g. ["domain:payments","capability:reporting"]

class FSS(BaseModel):
    stories: List[FSSStory] = []

# ---------- PSS ----------
class PSS(BaseModel):
    paradigm: str
    style: List[str] = []
    tech_stack: List[str] = []

# ---------- Request wrapper ----------
class DiscoveryInputs(BaseModel):
    avc: AVC
    fss: FSS
    pss: PSS

class DiscoveryOptions(BaseModel):
    model: Optional[str] = None
    dry_run: bool = False
    validate: bool = True
    pack_key: Optional[str] = None
    pack_version: Optional[str] = None

class StartDiscoveryRequest(BaseModel):
    playbook_id: str
    workspace_id: UUID4
    inputs: DiscoveryInputs
    options: Optional[DiscoveryOptions] = None

# ---------- Persistence shape ----------
class DiscoveryRun(BaseModel):
    discovery_run_id: UUID4
    workspace_id: UUID4
    playbook_id: str
    inputs: DiscoveryInputs
    options: DiscoveryOptions = Field(default_factory=DiscoveryOptions)
    status: str = "created"  # created|running|completed|failed
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    result_summary: Optional[Dict[str, Any]] = None
    result_artifacts_ref: Optional[str] = None
    error: Optional[str] = None
