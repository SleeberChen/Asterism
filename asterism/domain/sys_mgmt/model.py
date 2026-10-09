"""系统管理领域模型（仅独立部署形态启用，P3 §7.1 / P0 CON05）。

**分层建模规范**：领域层实体 / 值对象用 ``dataclass``，不引入 Pydantic（保持领域纯净）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass
class User:
    """系统用户（凭据字段不在本模型内，TC-14）。"""

    id: str
    tenant_id: str
    name: str
    roles: List[str] = field(default_factory=list)


@dataclass
class Role:
    """角色（权限为功能权限标识列表）。"""

    id: str
    tenant_id: str
    name: str
    permissions: List[str] = field(default_factory=list)


@dataclass
class MenuItem:
    """菜单项。"""

    id: str
    tenant_id: str
    title: str
    path: str
