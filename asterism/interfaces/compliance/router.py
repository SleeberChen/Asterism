"""安全合规路由（`APP-COMPLIANCE`）。

提供：鉴权判定 / 审计查询 / break-glass 申请。
注：本应用是鉴权的**提供方**，自身路由不套 ``require_permission``（避免自引用）。

成功响应一律返回 ``ApiResult[<业务 Schema>]``（强制规范）；所有失败由全局异常处理器
（``asterism/main.py``）统一映射为 ``ApiResult.fail(...)`` 信封，路由内不手写
``JSONResponse(exc.to_dict())``。
"""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, Request

from asterism.application.compliance.use_case import (
    AuditQueryUseCase,
    AuthorizeUseCase,
    BreakGlassUseCase,
)
from asterism.interfaces.common.result import ApiResult
from asterism.interfaces.compliance.deps import resolve_tenant_context
from asterism.seedwork.context import TenantContext, reset_tenant_context, set_tenant_context
from .schemas import (
    AuditEventOut,
    AuthorizeRequest,
    BreakGlassGrantOut,
    BreakGlassRequest,
    DecisionOut,
)

router = APIRouter(prefix="/api/v1/compliance", tags=["compliance"])


@router.post("/authorize", response_model=ApiResult[DecisionOut])
async def authorize(
    request: Request,
    body: AuthorizeRequest,
    tenant: TenantContext = Depends(resolve_tenant_context),
) -> ApiResult[DecisionOut]:
    token = set_tenant_context(tenant)  # 框架统一注入隔离上下文（TC-12）
    try:
        use_case: AuthorizeUseCase = request.app.state.compliance_authorize_use_case
        decision = use_case.execute(body.resource, body.action, request_id=tenant.request_id)
        return ApiResult.ok(DecisionOut(**decision.__dict__))
    finally:
        reset_tenant_context(token)


@router.get("/audit", response_model=ApiResult[List[AuditEventOut]])
async def audit_query(
    request: Request,
    action: Optional[str] = None,
    limit: int = 50,
    tenant: TenantContext = Depends(resolve_tenant_context),
) -> ApiResult[List[AuditEventOut]]:
    token = set_tenant_context(tenant)
    try:
        use_case: AuditQueryUseCase = request.app.state.compliance_audit_query_use_case
        events = use_case.execute(action=action, limit=limit)
        return ApiResult.ok([AuditEventOut(**e.__dict__) for e in events])
    finally:
        reset_tenant_context(token)


@router.post("/break-glass", response_model=ApiResult[BreakGlassGrantOut])
async def break_glass(
    request: Request,
    body: BreakGlassRequest,
    tenant: TenantContext = Depends(resolve_tenant_context),
) -> ApiResult[BreakGlassGrantOut]:
    token = set_tenant_context(tenant)
    try:
        use_case: BreakGlassUseCase = request.app.state.compliance_break_glass_use_case
        grant = use_case.execute(
            body.resource,
            approver=body.approver,
            ticket_id=body.ticket_id,
            ttl_seconds=body.ttl_seconds,
            request_id=tenant.request_id,
        )
        return ApiResult.ok(BreakGlassGrantOut(**grant.__dict__))
    finally:
        reset_tenant_context(token)
