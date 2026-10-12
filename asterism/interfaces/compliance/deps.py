"""跨应用复用的鉴权依赖（`APP-COMPLIANCE` 提供，其余应用路由只读复用）。

按 P3 §5 单写者表：**认证态 / 授权判定的权威写者＝`APP-COMPLIANCE`**，其余应用经契约
IC-07 读取判定，禁止各自实现鉴权（防重复实现、防口径漂移）。

用法（在其他应用的路由中）：:

    from asterism.interfaces.compliance.deps import resolve_tenant_context, require_permission

    @router.post("/query")
    async def query(
        tenant: TenantContext = Depends(resolve_tenant_context),
        decision: Decision = Depends(require_permission("rag", "read")),
    ): ...

说明：
- ``resolve_tenant_context`` 是**隔离上下文的统一注入点**（TC-12），各应用路由应复用它，
  不再各自实现 ``_resolve_tenant``。
- ``require_permission`` 为**可选**鉴权开关：判定由 `APP-COMPLIANCE` 完成并留痕；
  未装配鉴权用例时拒绝服务（不兜底）。演示策略要求请求带 ``X-User-Id``，
  管理员类动作须 ``X-User-Id: admin``。
- 鉴权 / 隔离相关的拒绝一律抛 ``AsterismError``，由全局异常处理器统一映射为
  响应信封（与业务错误同构，强制规范），不在本文件手写 ``HTTPException``。
"""

from __future__ import annotations

import uuid
from typing import Optional

from fastapi import Depends, Header, Request

from asterism.application.compliance.use_case import AuthorizeUseCase
from asterism.domain.compliance.model import Decision
from asterism.seedwork.context import (
    TenantContext,
    reset_tenant_context,
    set_tenant_context,
)
from asterism.seedwork.exceptions import BusinessError


def resolve_tenant_context(
    x_tenant_id: Optional[str] = Header(None),
    x_user_id: Optional[str] = Header(None),
    x_request_id: Optional[str] = Header(None),
) -> TenantContext:
    """统一的隔离上下文解析（框架注入点，TC-12；缺失即 401，不兜底）。

    真实鉴权由 `APP-COMPLIANCE` 八步链 M1 接管；本函数是骨架的统一入口。
    """
    if not x_tenant_id:
        # 缺隔离头 → 401（AST-ERR-2001）；由全局处理器统一为响应信封
        raise BusinessError("AST-ERR-2001", "缺少 X-Tenant-Id 头")
    return TenantContext(
        tenant_id=x_tenant_id,
        user_id=x_user_id,
        request_id=x_request_id or f"req-{uuid.uuid4().hex[:12]}",
    )


def require_permission(resource: str, action: str):
    """鉴权依赖工厂：调用 `APP-COMPLIANCE` 判定，拒绝返回 403（AST-ERR-2002）。

    判定失败（含鉴权未装配、权限不足、用例内业务异常）一律抛 `AsterismError`，
    由全局异常处理器统一映射为响应信封；本依赖仅负责隔离上下文注入与复位。
    """

    async def _dep(
        request: Request,
        tenant: TenantContext = Depends(resolve_tenant_context),
    ) -> Decision:
        use_case: Optional[AuthorizeUseCase] = getattr(
            request.app.state, "compliance_authorize_use_case", None
        )
        if use_case is None:
            # 鉴权未装配即拒绝服务（不兜底，与 TC-12 同口径）
            raise BusinessError("AST-ERR-2002", "鉴权未装配，拒绝服务")

        token = set_tenant_context(tenant)  # 用例从隔离上下文取租户
        try:
            decision = use_case.execute(resource, action, request_id=tenant.request_id)
        finally:
            # 无论判定成功与否都复位隔离上下文，避免泄漏到下一请求
            reset_tenant_context(token)

        if not decision.allowed:
            raise BusinessError("AST-ERR-2002", decision.reason)
        return decision

    return _dep
