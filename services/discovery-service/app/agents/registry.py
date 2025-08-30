from __future__ import annotations

from typing import Dict, Optional

# Import any existing handcrafted agents you still want to support explicitly.
# from app.agents.some_legacy_agent import SomeLegacyAgent
from app.agents.generic_kind_agent import GenericKindAgent

# Explicit overrides by capability id (if you still have custom agents)
_OVERRIDES: Dict[str, object] = {
    # "capability.api_contracts": SomeLegacyAgent(),
    # keep empty if you want everything to go via GenericKindAgent
}

# Global generic fallback
_GENERIC = GenericKindAgent()


# Optional: keep any specialized agents you still want to use, otherwise:
def agent_for_capability(capability_id: str) -> Any:
    # One generic agent instance is fine; they're stateless
    return GenericKindAgent()


def register_override(capability_id: str, agent_obj) -> None:
    """Optional: allow runtime registration for experiments/tests."""
    _OVERRIDES[capability_id] = agent_obj


def resolve_kind_from_capability(capability_id: str, capability_map: Optional[dict]) -> Optional[str]:
    """
    Helper to find a canonical kind for a capability from the capability map produced in ingest.
    Expected shapes (best-effort):
      capability_map[capability_id] -> { "produces": { "kinds": ["cam.contract.api", ...] } }
    """
    if not capability_map:
        return None
    meta = capability_map.get(capability_id) or {}
    prod = meta.get("produces") or {}
    kinds = prod.get("kinds") or []
    if kinds:
        return kinds[0]
    # Fallbacks: direct kind field, or alias
    return meta.get("kind") or meta.get("alias")
