"""安全合规路由（`APP-COMPLIANCE`）。

提供：鉴权判定 / 审计查询 / break-glass 申请。
注：本应用是鉴权的**提供方**，自身路由不套 ``require_permission``（避免自引用）。
"""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from asterism.application.compliance.use_case import (
    AuditQueryUseCase,
    AuthorizeUseCase,
    BreakGlassUseCase,
)
from asterism.interfaces.compliance.deps import resolve_tenant_context
from asterism.seedwork.context import TenantContext, reset_tenant_context, set_tenant_context
from asterism.seedwork.exceptions import AsterismError
from .schemas import (
    AuditEventOut,
    AuthorizeRequest,
    BreakGlassGrantOut,
    BreakGlassRequest,
    DecisionOut,
)

router = APIRouter(prefix="/api/v1/compliance", tags=["compliance"])


@router.post("/authorize", response_model=DecisionOut)
async def authorize(
    request: Request,
    body: AuthorizeRequest,
    tenant: TenantContext = Depends(resolve_tenant_context),
):
    token = set_tenant_context(tenant)  # 框架统一注入隔离上下文（TC-12）
    try:
        use_case: AuthorizeUseCase = request.app.state.compliance_authorize_use_case
        decision = use_case.execute(body.resource, body.action, request_id=tenant.request_id)
        return DecisionOut(**decision.__dict__)
    except AsterismError as exc:
        # 统一错误响应：AST-ERR 错误码 + 链路标识，不泄露内部细节（TC-16）
        return JSONResponse(status_code=exc.http_status, content=exc.to_dict())
    finally:
        reset_tenant_context(token)


@router.get("/audit", response_model=List[AuditEventOut])
async def audit_query(
    request: Request,
    action: Optional[str] = None,
    limit: int = 50,
    tenant: TenantContext = Depends(resolve_tenant_context),
):
    token = set_tenant_context(tenant)
    try:
        use_case: AuditQueryUseCase = request.app.state.compliance_audit_query_use_case
        events = use_case.execute(action=action, limit=limit)
        return [AuditEventOut(**e.__dict__) for e in events]
    except AsterismError as exc:
        return JSONResponse(status_code=exc.http_status, content=exc.to_dict())
    finally:
        reset_tenant_context(token)


@router.post("/break-glass", response_model=BreakGlassGrantOut)
async def break_glass(
    request: Request,
    body: BreakGlassRequest,
    tenant: TenantContext = Depends(resolve_tenant_context),
):
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
        return BreakGlassGrantOut(**grant.__dict__)
    except AsterismError as exc:
        return JSONResponse(status_code=exc.http_status, content=exc.to_dict())
    finally:
        reset_tenant_context(token)
