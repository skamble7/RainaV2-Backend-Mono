from typing import TypedDict, Any, List, Dict

class DiscoveryState(TypedDict, total=False):
    workspace_id: str
    playbook_id: str
    model_id: str
    inputs: dict
    options: dict
    plan: dict
    artifacts: List[dict]           # CAM artifacts ready for persistence
    validations: List[dict]
    logs: List[str]
    errors: List[str]
    context: Dict[str, Any]         # playbook, capabilities, etc.
