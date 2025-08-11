# app/agents/registry.py
from __future__ import annotations
from typing import Dict, Optional
from app.agents.spi import RainaAgent
from app.agents.micro.context_map import ContextMapAgent
from app.agents.micro.service_catalog import ServiceCatalogAgent
from app.agents.micro.api_contracts import ApiContractsAgent

# Map capability_id -> agent instance
_REGISTRY: Dict[str, RainaAgent] = {
    "cap.discover.context_map": ContextMapAgent(),
    "cap.catalog.services":     ServiceCatalogAgent(),
    "cap.contracts.api":        ApiContractsAgent(),
    # Add more as you convert them
}

def agent_for_capability(capability_id: str) -> Optional[RainaAgent]:
    return _REGISTRY.get((capability_id or "").strip())
