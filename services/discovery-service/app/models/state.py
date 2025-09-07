from typing import TypedDict, Any, List, Dict

class DiscoveryState(TypedDict, total=False):
    workspace_id: str
    playbook_id: str
    model_id: str
    inputs: dict
    options: dict
    plan: dict

    # Generated artifacts (pre-persist)
    artifacts: List[dict]

    # Validators & logging
    validations: List[dict]
    logs: List[str]
    errors: List[str]

    # Planner/ingest context, playbook metadata, etc.
    context: Dict[str, Any]

    # ⬇️ Explicitly include these so nothing ever drops them downstream
    run_artifacts: List[dict]
    artifacts_diff: Dict[str, Any]   # {new[], updated[], unchanged[], retired[], counts{...}}
    deltas: Dict[str, Any]           # {counts{...}}
    strategy: str                    # "baseline" | "delta"
