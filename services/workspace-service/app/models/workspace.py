# app/models/workspace.py
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Dict, Optional

from pydantic import BaseModel, Field, ConfigDict, field_validator


# --- Minimal enums/types ------------------------------------------------------

class AccessLevel(str, Enum):
    none = "none"
    read = "read"
    write = "write"
    owner = "owner"


# Map: platform_id -> access level
Visibility = Dict[str, AccessLevel]


# --- Create/Update payloads ---------------------------------------------------

class WorkspaceCreate(BaseModel):
    """
    Minimal create contract. If origin_platform is omitted, defaults to 'raina'
    (or injected via auth middleware). Visibility defaults to {origin_platform: owner}.
    """
    name: str = Field(min_length=1, max_length=200)
    description: Optional[str] = None
    created_by: Optional[str] = None

    # NEW (minimal additions)
    origin_platform: Optional[str] = Field(
        default=None,
        description="Platform that initiated this workspace"
    )
    visibility: Optional[Visibility] = Field(
        default=None,
        description="Per-platform ACL: {'renova': 'owner', 'raina': 'read', ...}",
    )

    @field_validator("origin_platform")
    @classmethod
    def _normalize_platform(cls, v: Optional[str]) -> Optional[str]:
        return v.lower() if isinstance(v, str) else v

    @field_validator("visibility")
    @classmethod
    def _normalize_visibility_keys(cls, v: Optional[Visibility]) -> Optional[Visibility]:
        if v is None:
            return v
        return {k.lower(): AccessLevel(vv) for k, vv in v.items()}


class WorkspaceUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = None

    # Allow thin visibility update
    visibility: Optional[Visibility] = None

    @field_validator("visibility")
    @classmethod
    def _normalize_visibility_keys(cls, v: Optional[Visibility]) -> Optional[Visibility]:
        if v is None:
            return v
        return {k.lower(): AccessLevel(vv) for k, vv in v.items()}


# --- DB / response model ------------------------------------------------------

class Workspace(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="allow")

    id: str = Field(..., alias="_id")  # ← still the canonical workspace ID
    name: str
    description: Optional[str] = None
    created_by: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    # NEW
    origin_platform: Optional[str] = None
    visibility: Visibility = Field(default_factory=dict)

    @field_validator("origin_platform")
    @classmethod
    def _normalize_platform(cls, v: Optional[str]) -> Optional[str]:
        return v.lower() if isinstance(v, str) else v

    @field_validator("visibility")
    @classmethod
    def _normalize_visibility_keys(cls, v: Visibility) -> Visibility:
        return {k.lower(): AccessLevel(vv) for k, vv in (v or {}).items()}
