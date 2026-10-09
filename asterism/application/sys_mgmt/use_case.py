"""系统管理用例（仅独立部署形态；并入星云不启用）。"""

from __future__ import annotations

from typing import List

from asterism.domain.sys_mgmt.model import MenuItem, Role, User
from asterism.domain.sys_mgmt.ports import UserDirectoryPort
from asterism.seedwork.context import require_tenant_context


class ListDirectoryUseCase:
    """目录查询（用户 / 角色 / 菜单），租户隔离由框架注入上下文保证（TC-12）。"""

    def __init__(self, directory: UserDirectoryPort) -> None:
        self._directory = directory

    def users(self) -> List[User]:
        ctx = require_tenant_context()
        return self._directory.list_users(ctx.tenant_id)

    def roles(self) -> List[Role]:
        ctx = require_tenant_context()
        return self._directory.list_roles(ctx.tenant_id)

    def menus(self) -> List[MenuItem]:
        ctx = require_tenant_context()
        return self._directory.list_menus(ctx.tenant_id)
