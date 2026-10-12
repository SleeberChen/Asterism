"""BC-MODEL 厂商管理用例（应用层门面，全链路异步）。

对外暴露全量 CRUD：登记厂商 / 登记模型 / 列厂商 / 查厂商 / 列模型 / 启停厂商 / 删厂商 / 删模型。
组合 ``ModelProviderOnboardingService`` + 仓储；统一从隔离上下文读取 ``tenant_id``（TC-12），
错误映射为 AST-ERR（TC-16，不泄露堆栈 / SQL / 内网地址）。

错误映射：
- ``NotFoundError`` → AST-ERR-3003（404）
- ``ConcurrencyError`` → AST-ERR-3005（409）
- ``InvariantViolationError`` → AST-ERR-3001（400）
- 其余未预期 → AST-ERR-5001（500，保留因果链，不吞，TC-15）
"""

from __future__ import annotations

from typing import Optional

from asterism.domain.model.catalog import (
    ConcurrencyError,
    InvariantViolationError,
    Model,
    ModelSpec,
    NotFoundError,
    Vendor,
    VendorConfig,
)
from asterism.domain.model.service import ModelProviderOnboardingService
from asterism.domain.model.repository import VendorRepository
from asterism.seedwork.context import require_tenant_context
from asterism.seedwork.exceptions import AsterismError, BusinessError, SystemError


def _translate(exc: Exception, request_id: Optional[str]) -> AsterismError:
    """领域异常 → 统一 AST-ERR（TC-16：只暴露错误码 + 用户可读信息 + 链路标识）。"""
    if isinstance(exc, NotFoundError):
        return BusinessError("AST-ERR-3003", message=str(exc))
    if isinstance(exc, ConcurrencyError):
        return BusinessError("AST-ERR-3005", message=str(exc))
    if isinstance(exc, InvariantViolationError):
        return BusinessError("AST-ERR-3001", message=str(exc))
    if isinstance(exc, AsterismError):
        return exc
    return SystemError("AST-ERR-5001", request_id=request_id, cause=exc)


class ModelManagementUseCase:
    """厂商全量 CRUD 门面（租户行级隔离贯穿；version 乐观锁冲突映射 409）。"""

    def __init__(self, vendor_repo: VendorRepository) -> None:
        self._vendors = vendor_repo
        self._onboard = ModelProviderOnboardingService(vendor_repo)

    async def register_vendor(
        self,
        *,
        vendor_id: str,
        plugin_registration_ref: str,
        name: str,
        config: VendorConfig,
    ) -> Vendor:
        ctx = require_tenant_context()
        try:
            return await self._onboard.register_vendor(
                vendor_id=vendor_id,
                plugin_registration_ref=plugin_registration_ref,
                name=name,
                config=config,
                tenant_id=ctx.tenant_id,
            )
        except AsterismError:
            raise
        except Exception as exc:
            raise _translate(exc, ctx.request_id) from exc

    async def register_model(self, *, vendor_id: str, spec: ModelSpec) -> Model:
        ctx = require_tenant_context()
        try:
            vendor = await self._vendors.get_by_id(vendor_id, ctx.tenant_id)
            await self._onboard.register_model(vendor, spec)
            return next(m for m in vendor.models if m.model_id == spec.model_id)
        except AsterismError:
            raise
        except Exception as exc:
            raise _translate(exc, ctx.request_id) from exc

    async def list_vendors(self) -> list[Vendor]:
        ctx = require_tenant_context()
        try:
            return await self._vendors.scan(ctx.tenant_id)
        except AsterismError:
            raise
        except Exception as exc:
            raise _translate(exc, ctx.request_id) from exc

    async def get_vendor(self, *, vendor_id: str) -> Vendor:
        ctx = require_tenant_context()
        try:
            return await self._vendors.get_by_id(vendor_id, ctx.tenant_id)
        except AsterismError:
            raise
        except Exception as exc:
            raise _translate(exc, ctx.request_id) from exc

    async def list_models(self, *, vendor_id: str) -> list[Model]:
        ctx = require_tenant_context()
        try:
            return await self._vendors.list_models(vendor_id, ctx.tenant_id)
        except AsterismError:
            raise
        except Exception as exc:
            raise _translate(exc, ctx.request_id) from exc

    async def set_vendor_status(self, *, vendor_id: str, status: str, expected_version: int) -> Vendor:
        ctx = require_tenant_context()
        try:
            await self._vendors.set_status(vendor_id, status, expected_version, ctx.tenant_id)
            return await self._vendors.get_by_id(vendor_id, ctx.tenant_id)
        except AsterismError:
            raise
        except Exception as exc:
            raise _translate(exc, ctx.request_id) from exc

    async def delete_vendor(self, *, vendor_id: str) -> None:
        ctx = require_tenant_context()
        try:
            await self._vendors.delete(vendor_id, ctx.tenant_id)
        except AsterismError:
            raise
        except Exception as exc:
            raise _translate(exc, ctx.request_id) from exc

    async def delete_model(self, *, vendor_id: str, model_id: str) -> None:
        ctx = require_tenant_context()
        try:
            await self._vendors.delete_model(vendor_id, model_id, ctx.tenant_id)
        except AsterismError:
            raise
        except Exception as exc:
            raise _translate(exc, ctx.request_id) from exc

    # --- 供应商 API 管理：凭据轮换 / 连接配置更新（写操作，乐观锁冲突映射 409） ---
    async def rotate_vendor_credentials(
        self, *, vendor_id: str, new_credential_handle: str, expected_version: int
    ) -> Vendor:
        ctx = require_tenant_context()
        try:
            await self._vendors.replace_credential_handle(
                vendor_id, new_credential_handle, expected_version, ctx.tenant_id
            )
            return await self._vendors.get_by_id(vendor_id, ctx.tenant_id)
        except AsterismError:
            raise
        except Exception as exc:
            raise _translate(exc, ctx.request_id) from exc

    async def update_vendor_connection(
        self,
        *,
        vendor_id: str,
        access_protocol: str,
        base_url: str,
        default_timeout_budget_ms: int,
        expected_version: int,
    ) -> Vendor:
        ctx = require_tenant_context()
        try:
            await self._vendors.replace_connection_config(
                vendor_id, access_protocol, base_url, default_timeout_budget_ms, expected_version, ctx.tenant_id
            )
            return await self._vendors.get_by_id(vendor_id, ctx.tenant_id)
        except AsterismError:
            raise
        except Exception as exc:
            raise _translate(exc, ctx.request_id) from exc

    # --- 顶层跨厂商模型查询（只读；写操作仍走嵌套端点） ---
    async def list_all_models(self) -> list[tuple[str, Model]]:
        ctx = require_tenant_context()
        try:
            return await self._vendors.scan_models(ctx.tenant_id)
        except AsterismError:
            raise
        except Exception as exc:
            raise _translate(exc, ctx.request_id) from exc

    async def get_model(self, *, model_id: str) -> tuple[str, Model]:
        ctx = require_tenant_context()
        try:
            result = await self._vendors.get_model(model_id, ctx.tenant_id)
            if result is None:
                raise NotFoundError(f"模型不存在: {model_id}")
            return result
        except AsterismError:
            raise
        except Exception as exc:
            raise _translate(exc, ctx.request_id) from exc
