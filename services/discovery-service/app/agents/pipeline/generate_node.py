# app/pipeline/generate_node.py
from __future__ import annotations
from app.models.state import DiscoveryState
from app.agents.pipeline.agent_runner import run_agents

async def generate_node(state: DiscoveryState) -> DiscoveryState:
    if not state.get("plan") or not state["plan"].get("steps"):
        state["plan"] = {"steps": [{"id": "svc-1", "capability": "cap.catalog.services"}]}
    await run_agents(state)  # mutates state in-place, populates state["artifacts"]
    return state
