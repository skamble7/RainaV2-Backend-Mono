# services/discovery-service/app/models/discovery.py
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
    description: List[str] | str | None = None  # allow flexibility
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

    # Friendly metadata for the run
    title: Optional[str] = Field(default=None, max_length=200)
    description: Optional[str] = Field(default=None, max_length=2000)

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
    """
    Diff result by natural key (not IDs), for easier UI grouping:
      - new: present in this run, not in prior snapshot for this workspace
      - updated: present in both, but with changed content/fingerprint
      - unchanged: present in both, same content/fingerprint
      - retired: present previously, not produced in this run
    """
    new: List[str] = []
    updated: List[str] = []
    unchanged: List[str] = []
    retired: List[str] = []

class RunDeltas(BaseModel):
    """
    Aggregated counts derived from ArtifactsDiff.
    Keys SHOULD be: new, updated, unchanged, retired.
    (No 'deleted' key.)
    """
    counts: Dict[str, int] = Field(default_factory=dict)

class ValidationIssue(BaseModel):
    artifact_id: str
    severity: Literal["low", "medium", "high"]
    message: str

class RunSummary(BaseModel):
    """
    Minimal, non-redundant summary of execution.
    (IDs, title/description, etc. live on DiscoveryRun itself.)
    """
    validations: List[ValidationIssue] = []
    logs: List[str] = []
    started_at: datetime
    completed_at: Optional[datetime] = None
    duration_s: Optional[float] = None

# ─────────────────────────────────────────────────────────────
# Run persistence shape
# ─────────────────────────────────────────────────────────────
class DiscoveryRun(BaseModel):
    run_id: UUID4

    workspace_id: UUID4
    playbook_id: str
    inputs: DiscoveryInputs
    options: DiscoveryOptions = Field(default_factory=DiscoveryOptions)

    # Friendly metadata for the run (non-mandatory)
    title: Optional[str] = Field(default=None, max_length=200)
    description: Optional[str] = Field(default=None, max_length=2000)

    # Inputs identity & comparison vs workspace baseline
    input_fingerprint: Optional[str] = None       # sha256 over canonical(inputs)
    input_diff: Optional[InputsDiff] = None

    # Run intent (auto-detected and persisted)
    strategy: Literal["baseline", "delta"] = "delta"

    # All artifacts produced in this run (full objects)
    run_artifacts: List[Dict[str, Any]] = Field(default_factory=list)

    # Classification vs prior baseline snapshot
    artifacts_diff: Optional[ArtifactsDiff] = None
    deltas: Optional[RunDeltas] = None

    status: Literal["created", "running", "completed", "failed", "aborted"] = "created"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # Minimal, non-redundant summary
    run_summary: Optional[RunSummary] = None
