# pss_v1.py
from pydantic import BaseModel
class PSSv1(BaseModel):
    workspace_id: str
    paradigm: str  # e.g., "service-based"
    style_pack: str  # e.g., "microservices-pack-v1"