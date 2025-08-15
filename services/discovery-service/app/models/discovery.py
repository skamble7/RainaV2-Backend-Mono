from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field, UUID4

# ─────────────────────────────────────────────────────────────
# Inputs (AVC / FSS / PSS)
# ─────────────────────────────────────────────────────────────
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

class FSSStory(BaseModel):
    key: str
    title: str
    description: str
    acceptance_criteria: List[str] = []
    tags: List[str] = []  # e.g., ["domain:auth","capability:batch-orchestration"]

class FSS(BaseModel):
    stories: List[FSSStory] = []

class PSS(BaseModel):
    paradigm: str
    style: List[str] = []
    tech_stack: List[str] = []

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

# ─────────────────────────────────────────────────────────────
# Diffs & summaries
# ─────────────────────────────────────────────────────────────
class AVCDiff(BaseModel):
    added_goals: List[str] = []
    removed_goals: List[str] = []
    updated_goals: List[Dict[str, Any]] = []   # { id, fields:[...] }
    added_vision: List[str] = []
    removed_vision: List[str] = []
    added_nfrs: List[str] = []
    removed_nfrs: List[str] = []

class FSSDiff(BaseModel):
    added_keys: List[str] = []
    removed_keys: List[str] = []
    updated: List[Dict[str, Any]] = []         # { key, fields:[...] }

class PSSDiff(BaseModel):
    paradigm_changed: bool = False
    style_added: List[str] = []
    style_removed: List[str] = []
    tech_added: List[str] = []
    tech_removed: List[str] = []

class InputsDiff(BaseModel):
    avc: AVCDiff = Field(default_factory=AVCDiff)
    fss: FSSDiff = Field(default_factory=FSSDiff)
    pss: PSSDiff = Field(default_factory=PSSDiff)

class ArtifactsDiff(BaseModel):
    new: List[str] = []        # artifact_ids
    updated: List[str] = []
    unchanged: List[str] = []
    retired: List[str] = []

# ─────────────────────────────────────────────────────────────
# Run persistence shape
# ─────────────────────────────────────────────────────────────
class DiscoveryRun(BaseModel):
    run_id: UUID4

    workspace_id: UUID4
    playbook_id: str
    inputs: DiscoveryInputs
    options: DiscoveryOptions = Field(default_factory=DiscoveryOptions)

    # Inputs identity & comparison vs workspace baseline
    input_fingerprint: Optional[str] = None       # sha256 over canonical(inputs)
    input_diff: Optional[InputsDiff] = None

    # Run intent + artifact summary
    strategy: Literal["baseline", "delta", "rebuild"] = "delta"
    artifacts_diff: Optional[ArtifactsDiff] = None

    status: Literal["created", "running", "completed", "failed", "aborted"] = "created"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    result_summary: Optional[Dict[str, Any]] = None
    result_artifacts_ref: Optional[str] = None
    error: Optional[str] = None
