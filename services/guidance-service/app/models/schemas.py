from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

class GuidanceGenerateRequest(BaseModel):
    workspace_id: str
    artifact_kinds: Optional[List[str]] = None   # e.g., ["service_contract","context_map","erd","sequence"]
    sections: Optional[List[str]] = None
    model_id: Optional[str] = None
    temperature: Optional[float] = None
    dry_run: bool = False
    include_pdf: bool = False

class GuidanceSection(BaseModel):
    id: str
    title: str
    content_md: str
    measures: Optional[List[str]] = None
    links: Optional[List[str]] = None

class GuidanceDocument(BaseModel):
    doc_type: str = "tech_guidance"
    workspace_id: str
    title: str
    overview: Optional[GuidanceSection] = None
    service_catalog: Optional[GuidanceSection] = None
    apis: Optional[GuidanceSection] = None
    events: Optional[GuidanceSection] = None
    nfrs: Optional[GuidanceSection] = None
    topology: Optional[GuidanceSection] = None
    observability: Optional[GuidanceSection] = None
    ops_runbooks: Optional[GuidanceSection] = None
    adrs: Optional[GuidanceSection] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)   # source artifact IDs, model info

class GuidanceGenerateResponse(BaseModel):
    document: GuidanceDocument
    artifact_id: Optional[str] = None
    pdf_path: Optional[str] = None
