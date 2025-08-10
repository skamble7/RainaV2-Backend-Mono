from pydantic import BaseModel
from typing import List, Optional, Dict, Any

class GuidanceGeneratedEvent(BaseModel):
    event_type: str = "guidance.generated"
    document_artifact_id: str
    workspace_id: str
    source_artifact_ids: List[str]
    model_id: str
    duration_ms: int
    meta: Dict[str, Any] = {}
