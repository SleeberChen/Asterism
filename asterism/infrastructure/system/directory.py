"""用户目录实现（演示用，实现 ``UserDirectoryPort``；仅独立部署）。

生产：替换为持久化目录；并入星云形态由星云公共用户权限服务提供，本实现不装配。
演示数据非生产真实数据（TC-19）。
"""

from __future__ import annotations

from typing import Dict, List

from asterism.domain.system.model import MenuItem, Role, User
from asterism.domain.system.ports import UserDirectoryPort

DEMO_TENANT = "demo-tenant"


class InMemoryUserDirectory(UserDirectoryPort):
    """进程内目录（按租户隔离，缺失租户返回空列表而非越权数据）。"""

    def __init__(self) -> None:
        self._users: Dict[str, List[User]] = {
            DEMO_TENANT: [
                User(id="u1", tenant_id=DEMO_TENANT, name="演示用户", roles=["user"]),
                User(id="admin", tenant_id=DEMO_TENANT, name="演示管理员", roles=["admin"]),
            ]
        }
        self._roles: Dict[str, List[Role]] = {
            DEMO_TENANT: [
                Role(
                    id="r-user",
                    tenant_id=DEMO_TENANT,
                    name="普通用户",
                    permissions=["sys.read"],
                ),
                Role(
                    id="r-admin",
                    tenant_id=DEMO_TENANT,
                    name="管理员",
                    permissions=["sys.read", "sys.admin"],
                ),
            ]
        }
        self._menus: Dict[str, List[MenuItem]] = {
            DEMO_TENANT: [
                MenuItem(id="m1", tenant_id=DEMO_TENANT, title="知识库问答", path="/rag"),
                MenuItem(id="m2", tenant_id=DEMO_TENANT, title="系统管理", path="/sys"),
            ]
        }

    def list_users(self, tenant_id: str) -> List[User]:
        return list(self._users.get(tenant_id, []))

    def list_roles(self, tenant_id: str) -> List[Role]:
        return list(self._roles.get(tenant_id, []))

    def list_menus(self, tenant_id: str) -> List[MenuItem]:
        return list(self._menus.get(tenant_id, []))
