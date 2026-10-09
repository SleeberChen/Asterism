"""安全合规接口层请求 / 响应 Schema（Pydantic v2）。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class AuthorizeRequest(BaseModel):
    resource: str = Field(..., min_length=1, max_length=200, description="目标资源")
    action: str = Field(..., min_length=1, max_length=64, description="动作（read/write/admin）")


class DecisionOut(BaseModel):
    allowed: bool
    reason: str
    tenant_id: str
    user_id: Optional[str] = None
    resource: str
    action: str


class AuditEventOut(BaseModel):
    tenant_id: str
    user_id: Optional[str] = None
    action: str
    resource: str
    outcome: str
    request_id: Optional[str] = None
    detail: Dict[str, Any] = {}


class BreakGlassRequest(BaseModel):
    resource: str = Field(..., min_length=1, max_length=200, description="目标资源")
    approver: str = Field(..., min_length=1, max_length=64, description="审批人")
    ticket_id: str = Field(..., min_length=1, max_length=64, description="审批工单号")
    ttl_seconds: int = Field(900, ge=1, le=3600, description="短时效（秒，上限 1 小时）")


class BreakGlassGrantOut(BaseModel):
    tenant_id: str
    user_id: str
    resource: str
    approver: str
    ticket_id: str
    ttl_seconds: int
    read_only: bool
    redacted: bool
    audit_required: bool


__all__ = [
    "AuthorizeRequest",
    "DecisionOut",
    "AuditEventOut",
    "BreakGlassRequest",
    "BreakGlassGrantOut",
    "List",
]
