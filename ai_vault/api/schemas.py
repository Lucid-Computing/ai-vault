"""Pydantic request/response schemas for the API."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


# --- Resource schemas ---

class ResourceCreate(BaseModel):
    name: str = Field(max_length=200)
    resource_type: str = Field(pattern="^(secret|file|mcp_tool)$")
    access_level: str = Field(default="red", pattern="^(red|yellow|green)$")
    value: Optional[str] = None
    file_path: Optional[str] = None
    mcp_server_url: Optional[str] = None
    mcp_tool_name: Optional[str] = None
    service: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[list[str]] = None


class ResourceUpdate(BaseModel):
    access_level: Optional[str] = Field(default=None, pattern="^(red|yellow|green)$")
    description: Optional[str] = None
    tags: Optional[list[str]] = None
    service: Optional[str] = None


class ResourceResponse(BaseModel):
    id: str
    name: str
    resource_type: str
    access_level: str
    file_path: Optional[str] = None
    mcp_server_url: Optional[str] = None
    mcp_tool_name: Optional[str] = None
    service: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[list[str]] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    last_accessed_at: Optional[datetime] = None
    access_count: int = 0

    model_config = {"from_attributes": True}


# --- Rule schemas ---

class RuleCreate(BaseModel):
    resource_id: str
    rule_type: str = Field(pattern="^(approve_each_use|max_uses_per_hour|purpose_required|time_window)$")
    enabled: bool = True
    max_uses: Optional[int] = None
    allowed_start_hour: Optional[int] = Field(default=None, ge=0, le=23)
    allowed_end_hour: Optional[int] = Field(default=None, ge=0, le=23)


class RuleUpdate(BaseModel):
    enabled: Optional[bool] = None
    max_uses: Optional[int] = None
    allowed_start_hour: Optional[int] = Field(default=None, ge=0, le=23)
    allowed_end_hour: Optional[int] = Field(default=None, ge=0, le=23)


class RuleResponse(BaseModel):
    id: str
    resource_id: str
    rule_type: str
    enabled: bool
    max_uses: Optional[int] = None
    allowed_start_hour: Optional[int] = None
    allowed_end_hour: Optional[int] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# --- Activity schemas ---

class ActivityResponse(BaseModel):
    id: str
    timestamp: Optional[datetime] = None
    action: str
    resource_name: str
    resource_id: str
    caller: Optional[str] = None
    success: bool
    details: Optional[dict[str, Any]] = None

    model_config = {"from_attributes": True}


# --- Approval schemas ---

class ApprovalResponse(BaseModel):
    id: str
    resource_id: str
    resource_name: str
    purpose: Optional[str] = None
    caller: Optional[str] = None
    status: str
    requested_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    decision_reason: Optional[str] = None
    ttl_seconds: int = 300

    model_config = {"from_attributes": True}


class ApprovalDecision(BaseModel):
    reason: Optional[str] = None


# --- Overview schema ---

class TopResourceItem(BaseModel):
    id: str
    name: str
    resource_type: str
    access_level: str
    access_count: int

    model_config = {"from_attributes": True}


class RecentActivityItem(BaseModel):
    id: str
    timestamp: Optional[datetime] = None
    action: str
    resource_name: str
    success: bool

    model_config = {"from_attributes": True}


class PendingApprovalItem(BaseModel):
    id: str
    resource_name: str
    purpose: Optional[str] = None
    caller: Optional[str] = None
    requested_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class OverviewResponse(BaseModel):
    total_resources: int
    resources_by_level: dict[str, int]
    resources_by_type: dict[str, int]
    pending_approvals: int
    total_accesses: int
    recent_activity_count: int
    top_resources: list[TopResourceItem] = []
    pending_approval_list: list[PendingApprovalItem] = []
    recent_activities: list[RecentActivityItem] = []
