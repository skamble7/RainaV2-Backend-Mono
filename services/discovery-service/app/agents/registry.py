# app/agents/registry.py
# Maps capability_id -> agent instance and provides a single helper for lookups.

from __future__ import annotations
from typing import Dict, Optional

from app.agents.spi import RainaAgent

# Microservices agents
from app.agents.micro.context_map import ContextMapAgent
from app.agents.micro.service_catalog import ServiceCatalogAgent
from app.agents.micro.api_contracts import ApiContractsAgent
from app.agents.micro.domain_erd import DomainErdAgent
from app.agents.micro.sequence_diagram import SequenceDiagramAgent
from app.agents.micro.component_diagram import ComponentDiagramAgent
from app.agents.micro.deployment_topology import DeploymentTopologyAgent
from app.agents.micro.authz_policies import AuthzPoliciesAgent
from app.agents.micro.app_workflows import AppWorkflowsAgent

# capability_id → concrete agent instance
_REGISTRY: Dict[str, RainaAgent] = {
    # Core discovery
    "cap.discover.context_map": ContextMapAgent(),
    "cap.catalog.services":     ServiceCatalogAgent(),
    "cap.contracts.api":        ApiContractsAgent(),

    # Diagrams & models
    "cap.generate.domain_diagrams": DomainErdAgent(),
    "cap.generate.sequence":        SequenceDiagramAgent(),
    "cap.generate.component":       ComponentDiagramAgent(),

    # Platform/NFR/Security/Workflows
    "cap.deploy.topology":          DeploymentTopologyAgent(),
    "cap.security.authz":           AuthzPoliciesAgent(),
    "cap.workflows.app":            AppWorkflowsAgent(),
}

def agent_for_capability(capability_id: str) -> Optional[RainaAgent]:
    """
    Look up the agent instance for a given capability_id.
    """
    return _REGISTRY.get((capability_id or "").strip())

__all__ = ["agent_for_capability"]
