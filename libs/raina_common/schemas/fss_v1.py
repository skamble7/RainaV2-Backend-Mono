# fss_v1.py
from pydantic import BaseModel
class FeatureStory(BaseModel):
    id: str
    title: str
    description: str
class FSSv1(BaseModel):
    workspace_id: str
    stories: list[FeatureStory]