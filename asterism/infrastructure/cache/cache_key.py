"""缓存键构造器（P5 TC-13：缓存键强制含隔离维度 ``tenant_id``）。

统一入口：所有缓存键必须经 :func:`build_cache_key` 构造，禁止业务代码手工拼键
（TC-12 同口径：隔离条件由框架统一注入）。
"""

from __future__ import annotations

from typing import Iterable, Optional, Sequence


def build_cache_key(*parts: str, tenant_id: str) -> str:
    """构造缓存键，强制前缀包含 ``tenant_id``。

    :param parts: 业务维度片段（命名空间 / 实体 / 版本等）。
    :param tenant_id: 隔离维度，缺省即抛 ``AST-ERR-2004``（隔离上下文缺失，不兜底）。
    :raises BusinessError: 当 ``tenant_id`` 为空（禁止无隔离键，TC-13 最高严重级）。
    """
    from asterism.seedwork.exceptions import BusinessError

    if not tenant_id:
        # 隔离维度缺失：拒绝构造无隔离键（对应 AST-ERR-2004 语义）
        raise BusinessError("AST-ERR-2004", message="缓存键缺失隔离维度 tenant_id")
    safe_parts: Sequence[str] = [p for p in parts if p]
    return ":".join(["ck", tenant_id, *safe_parts])


def build_cache_key_from_context(*parts: str, tenant_id: Optional[str] = None) -> str:
    """从隔离上下文注入 ``tenant_id`` 构造键（框架统一注入，业务代码不得改 tenant 值）。"""
    from asterism.seedwork.context import require_tenant_context

    tid = tenant_id or require_tenant_context().tenant_id
    return build_cache_key(*parts, tenant_id=tid)
