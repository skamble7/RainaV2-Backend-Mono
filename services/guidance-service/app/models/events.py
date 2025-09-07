from pydantic import BaseModel
from typing import List, Optional, Dict, Any

class GuidanceGeneratedEvent(BaseModel):
    event_type: str = "guidance.generated"
    workspace_id: str
    workspace_name: str
    version: int
    filename_md: str
    filename_pdf: Optional[str] = None
    source_artifact_ids: List[str]
    model_id: str
    duration_ms: int
    meta: Dict[str, Any] = {}
