"""APP-SYSTEM 端口契约单元测试（仅独立部署形态启用）。

覆盖 `asterism/domain/system/ports.py`：UserDirectoryPort。
并入星云形态下由星云公共用户权限服务提供，本端口不装配（P3 §7.1）。
"""
from asterism.domain.system.model import MenuItem, Role, User
from asterism.domain.system.ports import UserDirectoryPort


class _FakeDirectory:
    def __init__(self):
        self._users = [User(id="u-1", tenant_id="t-1", name="Alice")]
        self._roles = [Role(id="r-1", tenant_id="t-1", name="admin")]
        self._menus = [MenuItem(id="m-1", tenant_id="t-1", title="概览", path="/overview")]

    def list_users(self, tenant_id):
        return [u for u in self._users if u.tenant_id == tenant_id]

    def list_roles(self, tenant_id):
        return [r for r in self._roles if r.tenant_id == tenant_id]

    def list_menus(self, tenant_id):
        return [m for m in self._menus if m.tenant_id == tenant_id]


def test_directory_port_satisfied_by_duck_typed_impl():
    assert isinstance(_FakeDirectory(), UserDirectoryPort)


def test_directory_port_is_tenant_scoped():
    impl = _FakeDirectory()
    assert len(impl.list_users("t-1")) == 1
    assert impl.list_users("t-other") == []
    assert impl.list_roles("t-1")[0].name == "admin"
    assert impl.list_menus("t-1")[0].path == "/overview"
