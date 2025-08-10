from typing import Dict, Any, List, Optional, Set, TypedDict

class GuidanceState(TypedDict, total=False):
    workspace_id: str
    artifact_kinds: List[str]
    sections: List[str]
    model_id: str
    inputs: Dict[str, Any]
    source_artifacts: List[Dict[str, Any]]
    draft_markdown: str
    structured: Dict[str, Any]
    validation: Dict[str, Any]
    persisted_artifact_id: str
