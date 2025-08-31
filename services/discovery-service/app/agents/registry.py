#services/discovery-service/app/agents/registry.py
from __future__ import annotations
from typing import Any

from app.agents.generic_kind_agent import GenericKindAgent

# For now, route every capability to the generic kind agent.
def agent_for_capability(capability_id: str) -> Any:
    return GenericKindAgent()

def register_override(capability_id: str, agent_obj) -> None:
    pass  # kept for future extensibility
