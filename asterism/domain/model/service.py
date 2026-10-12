"""BC-MODEL 领域服务（行为不进实体；callLLM 落服务 + ModelPort 端口）。

对应 ``bc-model/战术设计.md`` §4：统一模型调用服务 / 供应商准入服务 / 供应商切换服务。
``registerTool``/``registerMCP`` 为跨 BC 绑定，不在本 BC 内（经事件 + 绑定服务）。

全链路异步：服务方法均为协程（仓储与端口均为异步）。
"""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import AsyncIterator
from typing import Callable, Optional

from .catalog import (
    Vendor,
    VendorConfig,
    ModelSpec,
    ModelCapability,
    PromptTemplate,
    ModelRegisteredEvent,
    ModelFailoverEvent,
    InvariantViolationError,
    NotFoundError,
)
from .model import ModelChunk, ModelRequest, ModelResponse  # 复用现有调用 DTO（TC-12 隔离维度）
from .ports import ModelPort
from .repository import VendorRepository, PromptTemplateRepository


class ModelProviderOnboardingService:
    """供应商准入：登记厂商 + 建模型（IN1 注册项 1:1 唯一）。"""

    def __init__(self, vendor_repo: VendorRepository) -> None:
        self._vendors = vendor_repo

    async def register_vendor(
        self,
        *,
        vendor_id: str,
        plugin_registration_ref: str,
        name: str,
        config: VendorConfig,
        tenant_id: str,
    ) -> Vendor:
        if await self._vendors.get_by_plugin_ref(plugin_registration_ref, tenant_id) is not None:
            raise InvariantViolationError("插件注册项引用 1:1 冲突（IN1）")
        vendor = Vendor(
            vendor_id=vendor_id,
            plugin_registration_ref=plugin_registration_ref,
            name=name,
            config=config,
            status="停用",
            tenant_id=tenant_id,
            version=1,
        )
        await self._vendors.save(vendor)
        return vendor

    async def register_model(self, vendor: Vendor, spec: ModelSpec) -> ModelRegisteredEvent:
        vendor.create_model(spec)
        await self._vendors.save(vendor)
        model = next(m for m in vendor.models if m.model_id == spec.model_id)
        return ModelRegisteredEvent(
            vendor_id=vendor.vendor_id,
            model_name=model.name,
            capability_summary=model.capability.summary(),
        )


@dataclass
class InvocationResult:
    text: str
    tenant_id: str
    model: str
    vendor_id: str
    actual_model_id: str
    fallback: bool = False


class UnifiedModelInvocationService:
    """统一模型调用：渲染模板（纯领域）→ ModelPort 调用（基础设施，不进实体）。"""

    def __init__(
        self,
        vendor_repo: VendorRepository,
        template_repo: Optional[PromptTemplateRepository],
        provider_resolver: Callable[[Vendor], ModelPort],
    ) -> None:
        self._vendors = vendor_repo
        self._templates = template_repo
        self._resolve = provider_resolver

    async def call(
        self,
        *,
        tenant_id: str,
        vendor_id: str,
        model_id: str,
        template_id: Optional[str] = None,
        var_map: Optional[dict[str, str]] = None,
        max_tokens: int = 2048,
    ) -> InvocationResult:
        vendor = await self._vendors.get_by_id(vendor_id, tenant_id)
        model = await self._pick_model(vendor, model_id)
        prompt = await self._render_prompt(tenant_id, template_id, var_map or {})
        req = ModelRequest(tenant_id=tenant_id, prompt=prompt, model=model.model_id, max_tokens=max_tokens)
        port = self._resolve(vendor)
        resp: ModelResponse = await port.complete(req)
        return InvocationResult(
            text=resp.text,
            tenant_id=tenant_id,
            model=resp.model,
            vendor_id=vendor.vendor_id,
            actual_model_id=model.model_id,
            fallback=False,
        )

    async def _pick_model(self, vendor: Vendor, model_id: str):
        if model_id == "default":
            model = await self._vendors.get_default_model(vendor.vendor_id, vendor.tenant_id)
            if model is None:
                raise InvariantViolationError("未配置默认模型且未指定模型，拒绝调用（U-DM-11）")
            return model
        for m in vendor.models:
            if m.model_id == model_id:
                return m
        raise NotFoundError(f"模型不存在: {model_id}")

    async def _render_prompt(self, tenant_id: str, template_id: Optional[str], var_map: dict[str, str]) -> str:
        if not template_id:
            return var_map.get("prompt", "")
        tmpl = await self._templates.get_by_id(template_id, tenant_id)
        return tmpl.render(var_map)

    async def call_stream(
        self,
        *,
        tenant_id: str,
        vendor_id: str,
        model_id: str,
        template_id: Optional[str] = None,
        var_map: Optional[dict[str, str]] = None,
        max_tokens: int = 2048,
    ) -> "AsyncIterator[ModelChunk]":
        """统一模型调用（流式）：渲染模板（纯领域）→ ModelPort 流式产出（基础设施，不进实体）。

        逐片 yield ``ModelChunk``；首个 yield 前的解析异常（厂商 / 模型 / 模板缺失）照常抛出，
        由调用方决定映射；端口内部错误由适配器层映射为 ``ExternalDependencyError``。
        """
        vendor = await self._vendors.get_by_id(vendor_id, tenant_id)
        model = await self._pick_model(vendor, model_id)
        prompt = await self._render_prompt(tenant_id, template_id, var_map or {})
        req = ModelRequest(tenant_id=tenant_id, prompt=prompt, model=model.model_id, max_tokens=max_tokens)
        # 探测可选流式能力：无则回退为单次完整生成（单帧 finished），保持 SSE 契约
        port = self._resolve(vendor)
        streamer = getattr(port, "complete_stream", None)
        if streamer is not None:
            async for chunk in streamer(req):
                yield chunk
            return
        resp = await port.complete(req)
        yield ModelChunk(
            content=resp.text,
            tenant_id=resp.tenant_id,
            model=resp.model,
            request_id=resp.request_id,
            finished=True,
        )


class ModelFailoverService:
    """供应商切换：无可用回退目标时显式失败（IN4），有则回退并广播事件。"""

    def __init__(self, vendor_repo: VendorRepository) -> None:
        self._vendors = vendor_repo

    async def failover(
        self, *, failed_vendor_id: str, tenant_id: str, reason: str
    ) -> tuple[Vendor, ModelFailoverEvent]:
        failed = await self._vendors.get_by_id(failed_vendor_id, tenant_id)
        candidates = [
            v for v in await self._vendors.list_by_status("启用", tenant_id) if v.vendor_id != failed.vendor_id
        ]
        if not candidates:
            raise InvariantViolationError("无可用回退目标，显式失败（IN4）")
        target = candidates[0]
        return target, ModelFailoverEvent(
            vendor_id=failed.vendor_id, reason=reason, target_vendor_id=target.vendor_id
        )
