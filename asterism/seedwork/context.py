"""八通道隔离上下文（P5 §14.4.1 / P4 第 8 章）。

隔离上下文由框架统一注入（TC-12：业务代码禁止手工拼隔离条件）。业务代码只读取
``tenant_id`` 等字段，不得自行构造过滤条件。

``tenant_id`` 字段级隔离贯穿八通道（租户 / 用户 / 请求 / 会话 / 权限 / 数据 / 平面 / 审计）。
本内核承载「租户 / 用户 / 请求」三要素载体；其余通道在各自子系统中复用该上下文。
"""

from __future__ import annotations

from contextvars import ContextVar, Token
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class TenantContext:
    """隔离上下文载体（不可变，避免业务代码意外改写）。"""

    tenant_id: str
    user_id: Optional[str] = None
    request_id: Optional[str] = None


# 默认 None：未注入上下文时显式报错（AST-ERR-2004，拒绝服务、不兜底，P5 §14.4.3）
tenant_context_var: ContextVar[Optional[TenantContext]] = ContextVar(
    "asterism_tenant_context", default=None
)


def get_tenant_context() -> Optional[TenantContext]:
    """读取当前隔离上下文（可能为 None，调用方须处理缺失）。"""
    return tenant_context_var.get()


def require_tenant_context() -> TenantContext:
    """读取隔离上下文，缺失即抛 ``AST-ERR-2004``（不兜底）。"""
    from .exceptions import BusinessError

    ctx = tenant_context_var.get()
    if ctx is None:
        raise BusinessError("AST-ERR-2004")
    return ctx


def set_tenant_context(ctx: TenantContext) -> Token:
    """注入隔离上下文（接口层 / 中间件在请求入口调用）。"""
    return tenant_context_var.set(ctx)


def reset_tenant_context(token: Token) -> None:
    """复位隔离上下文（请求结束时调用，避免泄漏到下一请求）。"""
    tenant_context_var.reset(token)
