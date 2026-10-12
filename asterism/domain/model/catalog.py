"""BC-MODEL 领域聚合（Option A + 提示词模板草稿）。

纯领域层：``dataclass``，无 IO、无框架依赖、无 Pydantic（保持领域纯净，TC-09 依赖倒置）。
对应 ``20-design/P6-详细设计/bc-model`` Option A 修订 + ``output/model-design-draft.md``。

行为归属（DMP-19 待登记）：``callLLM`` 不落实体（落 ``UnifiedModelInvocationService`` + ``ModelPort``
端口）；``registerTool``/``registerMCP`` 为跨 BC 绑定，不进实体。实体只持领域状态与纯领域行为。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# 领域错误
# ---------------------------------------------------------------------------
class DomainError(Exception):
    """领域层基础错误。"""


class InvariantViolationError(DomainError):
    """聚合不变量被破坏（业务拒绝）。"""


class ConcurrencyError(DomainError):
    """乐观锁冲突（映射 HTTP 409）。"""


class TemplateRenderError(DomainError):
    """模板占位符无法解析（缺值且无默认）。"""


class NotFoundError(DomainError):
    """聚合未找到。"""


# ---------------------------------------------------------------------------
# 值对象（不可变）
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class VendorConfig:
    """厂商配置值对象（不可变整体值；凭据轮换 = 整体替换，IN12）。"""

    access_protocol: str
    base_url: str
    credential_handle: str  # L3 机密：仅密文定位句柄，不含明文
    default_timeout_budget_ms: int

    def __post_init__(self) -> None:
        if not self.credential_handle:
            raise InvariantViolationError("凭据句柄必填且只存密文定位引用（IN3）")
        if self.default_timeout_budget_ms <= 0:
            raise InvariantViolationError("默认超时预算必须为正整数")


@dataclass(frozen=True)
class ModelCapability:
    """模型能力值对象（不可变）。"""

    context_window: int
    modalities: tuple[str, ...] = ()
    pricing_note: str = ""

    def __post_init__(self) -> None:
        if self.context_window <= 0:
            raise InvariantViolationError("context_window 必须为正整数")

    def summary(self) -> str:
        mods = ",".join(self.modalities) if self.modalities else "-"
        return f"ctx={self.context_window};mod={mods}"


@dataclass(frozen=True)
class PromptVariable:
    """模板变量值对象（不可变）。"""

    name: str
    type: str = "str"
    default: Optional[str] = None


# ---------------------------------------------------------------------------
# 聚合内实体：Model
# ---------------------------------------------------------------------------
@dataclass
class Model:
    """模型（Vendor 聚合内实体，非独立 AR；model_id 为聚合内局部标识）。"""

    model_id: str
    name: str
    capability: ModelCapability
    is_default: bool = False
    prompt_template_ids: list[str] = field(default_factory=list)

    def attach_template(self, template_id: str) -> None:
        if template_id not in self.prompt_template_ids:
            self.prompt_template_ids.append(template_id)


# ---------------------------------------------------------------------------
# 聚合根：PromptTemplate（独立 AR，草稿新增）
# ---------------------------------------------------------------------------
_PLACEHOLDER_RE = re.compile(r"\{\{\s*(\w+)\s*\}\}")


@dataclass
class PromptTemplate:
    """提示词模板（独立聚合根；可跨 Model / 跨 BC 复用，需稳定 ID 引用）。"""

    template_id: str
    name: str
    content: str
    variables: list[PromptVariable]
    version: int = 1
    model_affinity: Optional[str] = None
    status: str = "启用"  # 草稿 | 启用 | 停用
    tenant_id: str = ""

    def __post_init__(self) -> None:
        if self.status not in ("草稿", "启用", "停用"):
            raise InvariantViolationError("模板状态取值穷举于 草稿/启用/停用")
        self._validate_slots()

    def _validate_slots(self) -> None:
        declared = {v.name for v in self.variables}
        used = set(_PLACEHOLDER_RE.findall(self.content))
        if used and not used.issubset(declared):
            raise InvariantViolationError(f"模板占位符未声明变量：{sorted(used - declared)}")

    def render(self, var_map: dict[str, str]) -> str:
        """纯领域渲染：占位符取 var_map，缺则取变量默认；皆无则拒绝（不编造）。"""

        def repl(match: re.Match[str]) -> str:
            name = match.group(1)
            if name in var_map:
                return str(var_map[name])
            for var in self.variables:
                if var.name == name:
                    if var.default is not None:
                        return var.default
                    raise TemplateRenderError(f"占位符 {name} 无取值且无默认")
            raise TemplateRenderError(f"占位符 {name} 未声明")

        return _PLACEHOLDER_RE.sub(repl, self.content)

    def revise(self, content: str, variables: list[PromptVariable]) -> "PromptTemplate":
        """版本化修订：返回新版本实例；version 由仓储在 save 时统一递增（乐观锁）。"""
        return PromptTemplate(
            template_id=self.template_id,
            name=self.name,
            content=content,
            variables=list(variables),
            version=self.version,
            model_affinity=self.model_affinity,
            status=self.status,
            tenant_id=self.tenant_id,
        )


# ---------------------------------------------------------------------------
# 聚合根：Vendor（= ET-03）
# ---------------------------------------------------------------------------
@dataclass
class Vendor:
    """厂商聚合根（ET-03 演进）：身份 + VendorConfig(VO) + models(Model 集合)。"""

    vendor_id: str
    plugin_registration_ref: str  # → ET-02，1:1
    name: str
    config: VendorConfig
    status: str = "停用"  # 启用 | 停用
    tenant_id: str = ""
    version: int = 1
    models: list[Model] = field(default_factory=list)
    failover_target_ref: Optional[str] = None

    def __post_init__(self) -> None:
        if self.status not in ("启用", "停用"):
            raise InvariantViolationError("启用状态取值穷举于 启用/停用（IN2）")
        if not self.plugin_registration_ref:
            raise InvariantViolationError("插件注册项引用必填且唯一（IN1）")

    # --- 工厂 / 行为（纯领域；不修改 version，由仓储在 save 时递增） ---
    def create_model(self, spec: "ModelSpec") -> Model:
        """厂商产出模型（IN10 模型归属唯一；IN11 默认模型唯一）。"""
        if spec.is_default and any(m.is_default for m in self.models):
            raise InvariantViolationError("同一厂商默认模型至多一个（IN11）")
        model = Model(
            model_id=spec.model_id,
            name=spec.name,
            capability=spec.capability,
            is_default=spec.is_default,
        )
        self.models.append(model)
        return model

    def rotate_credentials(self, new_credential_handle: str) -> None:
        """凭据轮换 = 整体替换 VendorConfig（IN12）。"""
        if not new_credential_handle:
            raise InvariantViolationError("新凭据句柄必填")
        self.config = VendorConfig(
            access_protocol=self.config.access_protocol,
            base_url=self.config.base_url,
            credential_handle=new_credential_handle,
            default_timeout_budget_ms=self.config.default_timeout_budget_ms,
        )

    def enable(self) -> None:
        self.status = "启用"

    def disable(self) -> None:
        self.status = "停用"

    def set_failover(self, target_ref: Optional[str]) -> None:
        self.failover_target_ref = target_ref


@dataclass
class ModelSpec:
    """create_model 入参（工厂签名级）。"""

    model_id: str
    name: str
    capability: ModelCapability
    is_default: bool = False


# ---------------------------------------------------------------------------
# 领域事件（不进实体；至少一次投递 + 下游消费）
# ---------------------------------------------------------------------------
@dataclass
class ModelRegisteredEvent:
    type: str = "EVT-MODEL-REGISTERED"
    vendor_id: str = ""
    model_name: str = ""
    capability_summary: str = ""


@dataclass
class ModelFailoverEvent:
    type: str = "EVT-MODEL-FAILOVER"
    vendor_id: str = ""
    reason: str = ""
    target_vendor_id: str = ""


@dataclass
class PromptTemplatePublishedEvent:
    type: str = "EVT-PROMPT-TEMPLATE-PUBLISHED"
    template_id: str = ""
    name: str = ""
    version: int = 0
