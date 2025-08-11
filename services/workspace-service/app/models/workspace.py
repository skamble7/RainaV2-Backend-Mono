# app/models/workspace.py
from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime
from typing import Optional

class WorkspaceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: Optional[str] = None
    created_by: Optional[str] = None

class WorkspaceUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = None

class Workspace(BaseModel):
    # Optional but recommended
    model_config = ConfigDict(populate_by_name=True, extra="allow")
    id: str = Field(..., alias="_id")   # ← critical
    name: str
    description: Optional[str] = None
    created_by: Optional[str] = None
    created_at: datetime
    updated_at: datetime
