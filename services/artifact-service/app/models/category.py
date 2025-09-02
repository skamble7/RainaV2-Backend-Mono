# services/artifact-service/app/models/category.py
from __future__ import annotations

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict

class CategoryBase(BaseModel):
    """Shared fields for Category."""
    key: str = Field(..., min_length=2, pattern=r"^[a-z][a-z0-9_]*(\.[a-z0-9_]+)?$|^[a-z][a-z0-9_]*$")
    name: str = Field(..., min_length=2, max_length=80)
    description: Optional[str] = Field(default=None, max_length=2000)
    icon_svg: str = Field(..., min_length=10, description="SVG string. Prefer stroke/fill=currentColor.")

class CategoryCreate(CategoryBase):
    """Payload for creating/upserting a category."""
    pass

class CategoryUpdate(BaseModel):
    """Partial update payload."""
    name: Optional[str] = Field(default=None, min_length=2, max_length=80)
    description: Optional[str] = Field(default=None, max_length=2000)
    icon_svg: Optional[str] = Field(default=None, min_length=10)

class CategoryDoc(CategoryBase):
    """Stored Category document."""
    model_config = ConfigDict(populate_by_name=True)
    id: str = Field(alias="_id")
    created_at: datetime
    updated_at: datetime
