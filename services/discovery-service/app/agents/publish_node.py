from app.infra.rabbit import publish_event
from app.models.state import DiscoveryState

async def publish_node(state: DiscoveryState) -> DiscoveryState:
    publish_event("discovery.completed", state["workspace_id"], {
        "playbook_id": state["playbook_id"],
        "artifact_ids": state.get("context", {}).get("artifact_ids", []),
        "logs": state.get("logs", []),
        "validations": state.get("validations", [])
    })
    return state
