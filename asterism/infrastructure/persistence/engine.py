"""业务库异步引擎懒加载访问器（组合根 / 接口层复用）。

避免与 ``bootstrap/model.py`` 形成循环依赖（router 需引擎访问器，bootstrap 需 router），
故下沉到基础设施层。引擎为进程级单例，迁移幂等（``apply_migrations`` 按 schema_version 去重）。

约定：首次调用时按当前环境创建引擎并跑迁移；``reset_business_engine`` 仅测试用，
清空单例使下次按新环境重建。
"""

from __future__ import annotations

import asyncio
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncEngine

from .db import apply_migrations, make_engine

_BUSINESS_ENGINE: Optional[AsyncEngine] = None
_MIGRATION_DONE: bool = False
_LOCK = asyncio.Lock()


async def get_business_engine() -> AsyncEngine:
    """获取（懒加载并幂等迁移）业务库异步引擎。

    用 ``make_engine()`` 而非 ``make_business_engine()``：前者会读取 ``ASTERISM__DATABASE__URL``
    覆盖（sqlite 测试友好），后者直接取 ``DatabaseConfig.business.url``（MySQL 硬编码），忽略覆盖。
    """
    global _BUSINESS_ENGINE, _MIGRATION_DONE
    if _BUSINESS_ENGINE is None:
        _BUSINESS_ENGINE = make_engine()
    if not _MIGRATION_DONE:
        async with _LOCK:
            if not _MIGRATION_DONE:
                await apply_migrations(_BUSINESS_ENGINE)
                _MIGRATION_DONE = True
    return _BUSINESS_ENGINE


def reset_business_engine() -> None:
    """测试用：清空引擎单例与迁移标记，使下次调用按当前环境重建。"""
    global _BUSINESS_ENGINE, _MIGRATION_DONE
    _BUSINESS_ENGINE = None
    _MIGRATION_DONE = False
