# app/agents/spi.py
from __future__ import annotations
from typing import Protocol, TypedDict, List, Dict, Any, Optional

class ArtifactSelector(TypedDict, total=False):
    kind: str

class ContextEnvelope(TypedDict):
    avc: Dict[str, Any]
    fss: Dict[str, Any]
    pss: Dict[str, Any]
    artifacts: Dict[str, Any]  # read-only snapshot (can be {} for now)

class AgentResult(TypedDict, total=False):
    # Phase 1: we encode each output as an upsert-style patch to keep it future-proof.
    patches: List[Dict[str, Any]]        # e.g., {"op":"upsert","path":"/artifacts","value":{...}}
    tasks: Optional[List[Dict[str, Any]]]
    adrs: Optional[List[Dict[str, Any]]]
    telemetry: Optional[List[Dict[str, Any]]]

class RainaAgent(Protocol):
    id: str
    provides: List[ArtifactSelector]
    requires: List[ArtifactSelector]
    supports: Dict[str, List[str]]     # {"paradigms":[...], "styles":[...]}
    version: str

    async def run(self, ctx: ContextEnvelope, params: Dict[str, Any]) -> AgentResult: ...
