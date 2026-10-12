"""系统管理路由（`APP-SYSTEM`，仅独立部署形态装配）。

演示跨应用复用 `APP-COMPLIANCE` 的鉴权：目录查询（read）经 ``require_permission`` 判定，
拒绝返回 403（`AST-ERR-2002`）；判定结果由合规应用统一留痕。

成功响应一律返回 ``ApiResult[<业务 Schema>]``（强制规范）；所有失败由全局异常处理器
（``asterism/main.py``）统一映射为 ``ApiResult.fail(...)`` 信封，路由内不手写
``JSONResponse(exc.to_dict())``。
"""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, Request

from asterism.application.system.use_case import ListDirectoryUseCase
from asterism.domain.compliance.model import Decision
from asterism.interfaces.common.result import ApiResult
from asterism.interfaces.compliance.deps import require_permission, resolve_tenant_context
from asterism.seedwork.context import TenantContext, reset_tenant_context, set_tenant_context
from .schemas import MenuOut, RoleOut, UserOut

router = APIRouter(prefix="/api/v1/sys", tags=["system"])


def _use_case(request: Request) -> ListDirectoryUseCase:
    return request.app.state.system_directory_use_case


@router.get("/users", response_model=ApiResult[List[UserOut]])
async def list_users(
    request: Request,
    tenant: TenantContext = Depends(resolve_tenant_context),
    decision: Decision = Depends(require_permission("sys", "read")),
) -> ApiResult[List[UserOut]]:
    token = set_tenant_context(tenant)  # 框架统一注入隔离上下文（TC-12）
    try:
        return ApiResult.ok([UserOut(**u.__dict__) for u in _use_case(request).users()])
    finally:
        reset_tenant_context(token)


@router.get("/roles", response_model=ApiResult[List[RoleOut]])
async def list_roles(
    request: Request,
    tenant: TenantContext = Depends(resolve_tenant_context),
    decision: Decision = Depends(require_permission("sys", "read")),
) -> ApiResult[List[RoleOut]]:
    token = set_tenant_context(tenant)
    try:
        return ApiResult.ok([RoleOut(**r.__dict__) for r in _use_case(request).roles()])
    finally:
        reset_tenant_context(token)


@router.get("/menus", response_model=ApiResult[List[MenuOut]])
async def list_menus(
    request: Request,
    tenant: TenantContext = Depends(resolve_tenant_context),
    decision: Decision = Depends(require_permission("sys", "read")),
) -> ApiResult[List[MenuOut]]:
    token = set_tenant_context(tenant)
    try:
        return ApiResult.ok([MenuOut(**m.__dict__) for m in _use_case(request).menus()])
    finally:
        reset_tenant_context(token)
