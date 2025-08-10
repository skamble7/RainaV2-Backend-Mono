from pydantic import BaseModel, Field
from typing import Any, Dict, Optional

class AVC(BaseModel):
    summary: str
    goals: list[str] = []
    constraints: list[str] = []

class FSS(BaseModel):
    features: list[Dict[str, Any]] = []  # keep generic for now

class PSS(BaseModel):
    paradigm: str
    styles: list[str] = []
    tech_stack: list[str] = []

class DiscoveryInputs(BaseModel):
    avc: AVC
    fss: FSS
    pss: PSS

class DiscoveryOptions(BaseModel):
    model: str | None = None
    dry_run: bool = False
    validate: bool = True

class StartDiscoveryRequest(BaseModel):
    playbook_id: str
    inputs: DiscoveryInputs
    options: DiscoveryOptions | None = None
