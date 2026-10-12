"""BC-MODEL 厂商管理接口 Schema（Pydantic v2）+ 领域 → 响应映射。

字段级约束（长度 / 非空）在 Schema 层做初筛；业务不变量（状态穷举、默认模型唯一、凭据句柄必填）
由领域层 ``__post_init__`` 强制，违例映射 AST-ERR-3001（TC-16 不泄露细节）。
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from asterism.domain.model.catalog import Vendor, Model


class VendorRegisterRequest(BaseModel):
    """登记厂商：``status`` 固定为「停用」（领域默认值），由启停端点切换。"""

    vendor_id: str = Field(..., max_length=64, description="厂商 ID（租户内唯一）")
    plugin_registration_ref: str = Field(..., max_length=255, description="插件注册项引用（1:1，IN1）")
    name: str = Field(..., max_length=128, description="厂商名称")
    access_protocol: str = Field(..., max_length=64, description="访问协议（openai/anthropic/...）")
    base_url: str = Field(..., max_length=2048, description="基址 URL")
    credential_handle: str = Field(..., min_length=1, max_length=512, description="L3 凭据句柄（仅密文定位引用）")
    default_timeout_budget_ms: int = Field(..., gt=0, description="默认超时预算(ms)")
    failover_target_ref: Optional[str] = Field(None, max_length=255, description="回退目标引用（可选）")


class ModelRegisterRequest(BaseModel):
    """登记模型（聚合内实体，从属厂商）。"""

    model_id: str = Field(..., max_length=64, description="模型 ID（厂商内唯一）")
    name: str = Field(..., max_length=128, description="模型名称")
    context_window: int = Field(..., gt=0, description="上下文窗口(token)")
    modalities: list[str] = Field(default_factory=list, description="模态列表")
    pricing_note: str = Field("", max_length=512, description="计价说明")
    is_default: bool = Field(False, description="是否默认模型（厂商内至多一个，IN11）")


class VendorStatusRequest(BaseModel):
    """启停厂商：携带 ``expected_version`` 走乐观锁，冲突映射 409。"""

    status: str = Field(..., max_length=32, description="目标状态：启用 | 停用")
    expected_version: int = Field(..., description="期望基线版本（乐观锁）")


class VendorCredentialRequest(BaseModel):
    """供应商 API 凭据轮换：仅替换凭据句柄（L3 密文定位引用），保留连接配置。"""

    new_credential_handle: str = Field(..., min_length=1, max_length=512, description="L3 凭据句柄（仅密文定位引用）")
    expected_version: int = Field(..., description="期望基线版本（乐观锁）")


class VendorConnectionRequest(BaseModel):
    """供应商 API 连接配置更新（非机密部分）：替换协议 / 基址 / 超时预算，保留凭据句柄。"""

    access_protocol: str = Field(..., max_length=64, description="访问协议（openai/anthropic/...）")
    base_url: str = Field(..., max_length=2048, description="基址 URL")
    default_timeout_budget_ms: int = Field(..., gt=0, description="默认超时预算(ms)")
    expected_version: int = Field(..., description="期望基线版本（乐观锁）")


class ModelResponse(BaseModel):
    vendor_id: str
    model_id: str
    name: str
    context_window: int
    modalities: list[str]
    pricing_note: str
    is_default: bool
    prompt_template_ids: list[str]


class VendorResponse(BaseModel):
    vendor_id: str
    plugin_registration_ref: str
    name: str
    status: str
    version: int
    access_protocol: str
    base_url: str
    default_timeout_budget_ms: int
    failover_target_ref: Optional[str]
    models: list[ModelResponse]


def to_model_response(m: Model, vendor_id: str) -> ModelResponse:
    return ModelResponse(
        vendor_id=vendor_id,
        model_id=m.model_id,
        name=m.name,
        context_window=m.capability.context_window,
        modalities=list(m.capability.modalities),
        pricing_note=m.capability.pricing_note,
        is_default=m.is_default,
        prompt_template_ids=list(m.prompt_template_ids),
    )


def to_vendor_response(v: Vendor) -> VendorResponse:
    return VendorResponse(
        vendor_id=v.vendor_id,
        plugin_registration_ref=v.plugin_registration_ref,
        name=v.name,
        status=v.status,
        version=v.version,
        access_protocol=v.config.access_protocol,
        base_url=v.config.base_url,
        default_timeout_budget_ms=v.config.default_timeout_budget_ms,
        failover_target_ref=v.failover_target_ref,
        models=[to_model_response(m, v.vendor_id) for m in v.models],
    )
