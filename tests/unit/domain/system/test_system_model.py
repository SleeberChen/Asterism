"""APP-SYSTEM 领域模型单元测试（仅独立部署形态启用，P3 §7.1 / P0 CON05）。

覆盖 `asterism/domain/system/model.py`：User / Role / MenuItem。
"""
from asterism.domain.system.model import MenuItem, Role, User


def test_user_defaults_to_no_roles():
    u = User(id="u-1", tenant_id="t-1", name="Alice")
    assert u.roles == []


def test_user_roles_not_shared_between_instances():
    u1 = User(id="u-1", tenant_id="t-1", name="Alice")
    u2 = User(id="u-2", tenant_id="t-1", name="Bob")
    u1.roles.append("admin")
    assert u1.roles == ["admin"]
    assert u2.roles == []


def test_role_permissions():
    r = Role(
        id="r-1", tenant_id="t-1", name="admin", permissions=["sys:read", "sys:write"]
    )
    assert r.permissions == ["sys:read", "sys:write"]
    assert Role(id="r-2", tenant_id="t-1", name="viewer").permissions == []


def test_menu_item_fields():
    m = MenuItem(id="m-1", tenant_id="t-1", title="概览", path="/overview")
    assert (m.title, m.path) == ("概览", "/overview")
    assert m.tenant_id == "t-1"
