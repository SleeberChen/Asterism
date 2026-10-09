"""系统管理端口（领域层定义，基础设施实现；依赖倒置 TC-09）。"""

from __future__ import annotations

from typing import List, Protocol, runtime_checkable

from .model import MenuItem, Role, User


@runtime_checkable
class UserDirectoryPort(Protocol):
    """用户 / 角色 / 菜单目录。

    仅独立部署形态启用；并入星云由星云公共用户权限服务（`BC-TENANT` / `BC-PERM`）提供，
    本端口在该形态下不装配（P3 §7.1）。
    """

    def list_users(self, tenant_id: str) -> List[User]:
        ...

    def list_roles(self, tenant_id: str) -> List[Role]:
        ...

    def list_menus(self, tenant_id: str) -> List[MenuItem]:
        ...
