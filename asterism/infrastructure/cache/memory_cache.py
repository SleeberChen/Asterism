"""进程内缓存实现（本期落地；TC-18 单点容忍，已登记）。

约束：
- 键必须经 :func:`build_cache_key` 构造（含 tenant_id，TC-13）。
- 进程内 ``dict`` 缓存：仅适用于单进程部署；多进程 / 多副本场景本期明确登记为单点
  （P5 TC-18：允许登记为「本期容忍的单点」并写入附录 A）。
"""

from __future__ import annotations

from typing import Dict, Optional

from .cache_key import build_cache_key


class MemoryCache:
    """极简进程内键值缓存（演示用，非生产级分布式缓存）。"""

    def __init__(self) -> None:
        self._store: Dict[str, object] = {}

    def get(self, key: str) -> Optional[object]:
        return self._store.get(key)

    def set(self, key: str, value: object) -> None:
        self._store[key] = value

    def make_key(self, *parts: str, tenant_id: str) -> str:
        """经由统一构造器生成键（强制含 tenant_id）。"""
        return build_cache_key(*parts, tenant_id=tenant_id)
