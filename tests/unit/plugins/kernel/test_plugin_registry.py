"""插件内核注册表单元测试（TC-11：内核不反向依赖四类插件；四类插件互不依赖）。

覆盖 `asterism/plugins/kernel/registry.py` 与 `base.py`。
注册表为单一注册点，模型 / 工具 / 技能 / 记忆四类插件经此注册与发现。
"""
from asterism.plugins.kernel.base import Plugin, PluginKind
from asterism.plugins.kernel.registry import PluginRegistry, get_registry


class _RecPlugin:
    """最小插件实现，仅记录生命周期调用轨迹。"""

    def __init__(self, kind, name):
        self.kind = kind
        self.name = name
        self.trace = []

    def init(self):
        self.trace.append("init")

    def start(self):
        self.trace.append("start")

    def stop(self):
        self.trace.append("stop")


def test_register_invokes_init_and_is_retrievable():
    reg = PluginRegistry()
    p = _RecPlugin(PluginKind.MODEL, "m-1")
    reg.register(p)
    assert p.trace == ["init"]
    assert reg.get(PluginKind.MODEL, "m-1") is p


def test_get_missing_returns_none():
    reg = PluginRegistry()
    assert reg.get(PluginKind.TOOL, "nope") is None


def test_register_same_kind_and_name_overwrites():
    reg = PluginRegistry()
    p1 = _RecPlugin(PluginKind.MODEL, "m-1")
    p2 = _RecPlugin(PluginKind.MODEL, "m-1")
    reg.register(p1)
    reg.register(p2)
    assert reg.get(PluginKind.MODEL, "m-1") is p2
    assert len(reg.list_kind(PluginKind.MODEL)) == 1


def test_list_kind_filters_by_kind():
    reg = PluginRegistry()
    reg.register(_RecPlugin(PluginKind.MODEL, "m-1"))
    reg.register(_RecPlugin(PluginKind.TOOL, "t-1"))
    reg.register(_RecPlugin(PluginKind.MODEL, "m-2"))
    assert len(reg.list_kind(PluginKind.MODEL)) == 2
    assert len(reg.list_kind(PluginKind.TOOL)) == 1
    assert reg.list_kind(PluginKind.SKILL) == []


def test_start_and_stop_all_touch_every_plugin():
    reg = PluginRegistry()
    a = _RecPlugin(PluginKind.MODEL, "m-1")
    b = _RecPlugin(PluginKind.TOOL, "t-1")
    reg.register(a)
    reg.register(b)
    reg.start_all()
    reg.stop_all()
    assert a.trace == ["init", "start", "stop"]
    assert b.trace == ["init", "start", "stop"]


def test_fake_plugin_satisfies_plugin_protocol():
    assert isinstance(_RecPlugin(PluginKind.MEMORY, "mem-1"), Plugin)


def test_get_registry_is_process_singleton():
    r1 = get_registry()
    r2 = get_registry()
    assert r1 is r2
    assert isinstance(r1, PluginRegistry)
