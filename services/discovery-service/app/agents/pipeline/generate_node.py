# app/pipeline/generate_node.py
from __future__ import annotations
from typing import Any, Dict
from app.models.state import DiscoveryState
from app.agents.pipeline.agent_runner import run_agents

async def generate_node(state: DiscoveryState) -> DiscoveryState:
    """
    Phase 1 delegator:
    - Uses the new Agent Runner which executes capability-bound agents.
    - Keeps the 'artifacts' contract intact for persist_node.
    """
    # Fallback plan if none (keeps old behavior safe)
    if not state.get("plan") or not state["plan"].get("steps"):
        state["plan"] = {"steps": [{"id": "svc-1", "capability": "cap.catalog.services"}]}
    await run_agents(state)  # mutates state in-place
    return state
