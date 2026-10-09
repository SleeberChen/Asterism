"""系统管理路由（`APP-SYSMGMT`，仅独立部署形态装配）。

演示跨应用复用 `APP-COMPLIANCE` 的鉴权：目录查询（read）经 ``require_permission`` 判定，
拒绝返回 403（`AST-ERR-2002`）；判定结果由合规应用统一留痕。

"""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from asterism.application.sys_mgmt.use_case import ListDirectoryUseCase
from asterism.domain.compliance.model import Decision
from asterism.interfaces.compliance.deps import require_permission, resolve_tenant_context
from asterism.seedwork.context import TenantContext, reset_tenant_context, set_tenant_context
from asterism.seedwork.exceptions import AsterismError
from .schemas import MenuOut, RoleOut, UserOut

router = APIRouter(prefix="/api/v1/sys", tags=["sys_mgmt"])


def _use_case(request: Request) -> ListDirectoryUseCase:
    return request.app.state.sys_mgmt_directory_use_case


@router.get("/users", response_model=List[UserOut])
async def list_users(
    request: Request,
    tenant: TenantContext = Depends(resolve_tenant_context),
    decision: Decision = Depends(require_permission("sys", "read")),
):
    token = set_tenant_context(tenant)  # 框架统一注入隔离上下文（TC-12）
    try:
        return [UserOut(**u.__dict__) for u in _use_case(request).users()]
    except AsterismError as exc:
        return JSONResponse(status_code=exc.http_status, content=exc.to_dict())
    finally:
        reset_tenant_context(token)


@router.get("/roles", response_model=List[RoleOut])
async def list_roles(
    request: Request,
    tenant: TenantContext = Depends(resolve_tenant_context),
    decision: Decision = Depends(require_permission("sys", "read")),
):
    token = set_tenant_context(tenant)
    try:
        return [RoleOut(**r.__dict__) for r in _use_case(request).roles()]
    except AsterismError as exc:
        return JSONResponse(status_code=exc.http_status, content=exc.to_dict())
    finally:
        reset_tenant_context(token)


@router.get("/menus", response_model=List[MenuOut])
async def list_menus(
    request: Request,
    tenant: TenantContext = Depends(resolve_tenant_context),
    decision: Decision = Depends(require_permission("sys", "read")),
):
    token = set_tenant_context(tenant)
    try:
        return [MenuOut(**m.__dict__) for m in _use_case(request).menus()]
    except AsterismError as exc:
        return JSONResponse(status_code=exc.http_status, content=exc.to_dict())
    finally:
        reset_tenant_context(token)
