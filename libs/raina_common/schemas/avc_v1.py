# avc_v1.py
from pydantic import BaseModel
class AVCv1(BaseModel):
    workspace_id: str
    vision: str
    goals: list[str]