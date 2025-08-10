from app.models.state import DiscoveryState
from app.clients.capability_registry import fetch_playbook

async def ingest_node(state: DiscoveryState) -> DiscoveryState:
    playbook = await fetch_playbook(state["playbook_id"])
    state.setdefault("context", {})["playbook"] = playbook
    state.setdefault("logs", []).append("Playbook loaded")
    return state
