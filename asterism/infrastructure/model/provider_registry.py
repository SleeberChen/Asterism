"""按 ``access_protocol`` 选择供应商适配器（真实供应商即插即用，业务不感知具体供应商）。

- 协议 → 适配器工厂（输入 ``Vendor``，返回 ``ModelPort``）；工厂在调用时解析凭据（TC-02：
  明文只在调用供应商前读取一次）。
- 未知协议回退 ``StubModelAdapter``（演示 / 未接入真实供应商），保证链路不中断。

业务侧 ``UnifiedModelInvocationService`` 只调用 ``resolve_port(vendor)``，新增供应商只需在此
登记协议，无需改动编排代码（一切皆插件）。
"""
from __future__ import annotations

from typing import Callable

from asterism.domain.model.catalog import Vendor
from asterism.domain.model.ports import ModelPort
from asterism.infrastructure.model.credential import resolve_credential
from asterism.infrastructure.model.provider import StubModelAdapter
from asterism.infrastructure.model.siliconflow_provider import SiliconFlowAdapter

# protocol -> 工厂(Vendor) -> ModelPort
_REGISTRY: dict[str, Callable[[Vendor], ModelPort]] = {}


def register_protocol(protocol: str, factory: Callable[[Vendor], ModelPort]) -> None:
    _REGISTRY[protocol] = factory


def resolve_port(vendor: Vendor) -> ModelPort:
    """按厂商 access_protocol 选择适配器；未知协议回退桩。"""
    factory = _REGISTRY.get(vendor.config.access_protocol)
    if factory is None:
        return StubModelAdapter()
    return factory(vendor)


def _openai_factory(vendor: Vendor) -> ModelPort:
    """OpenAI 兼容协议（硅基流动等）：用厂商配置装配真实适配器，调用时按 handle 取秘钥。"""
    return SiliconFlowAdapter(
        base_url=vendor.config.base_url,
        api_key=resolve_credential(vendor.config.credential_handle),
        timeout_s=max(1.0, vendor.config.default_timeout_budget_ms / 1000.0),
    )


register_protocol("openai", _openai_factory)
register_protocol("siliconflow", _openai_factory)
