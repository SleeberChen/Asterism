"""契约测试 `T-CONTRACT-01` → `IC-01` 插件注册与生命周期契约。

测试意图（P3 02-应用间契约.md）：
- 模型 / 工具 / 技能 / 记忆四类插件**共用同一注册接口**（重复实现数 = 0）；
- 契约不一致注册拒绝率 = 100%。
"""
from __future__ import annotations

import pytest

from asterism.plugins.kernel.base import Plugin, PluginKind
from asterism.plugins.kernel.registry import PluginRegistry


class _Probe:
    """最小探针插件：记录生命周期调用，用于验证四类共用同一接口。"""

    def __init__(self, kind: PluginKind, name: str) -> None:
        self.kind = kind
        self.name = name
        self.trace: list[str] = []

    def init(self) -> None:
        self.trace.append("init")

    def start(self) -> None:
        self.trace.append("start")

    def stop(self) -> None:
        self.trace.append("stop")


ALL_KINDS = [PluginKind.MODEL, PluginKind.TOOL, PluginKind.SKILL, PluginKind.MEMORY]


def test_four_kinds_share_one_registration_interface():
    """四类插件经**同一个** `register` 注册：无按种类分裂的注册 API（重复实现数 = 0）。"""
    reg = PluginRegistry()
    probes = [_Probe(kind, f"{kind.value}-probe") for kind in ALL_KINDS]
    for p in probes:
        reg.register(p)  # 同一入口

    assert len(reg.list_kind(PluginKind.MODEL)) == 1
    assert len(reg.list_kind(PluginKind.TOOL)) == 1
    assert len(reg.list_kind(PluginKind.SKILL)) == 1
    assert len(reg.list_kind(PluginKind.MEMORY)) == 1


def test_shared_lifecycle_is_uniform_across_kinds():
    """生命周期（init/start/stop）对四类一致，且 `init` 仅在注册时触发一次。"""
    reg = PluginRegistry()
    probes = [_Probe(kind, f"{kind.value}-life") for kind in ALL_KINDS]
    for p in probes:
        reg.register(p)
    reg.start_all()
    reg.stop_all()

    for p in probes:
        assert p.trace == ["init", "start", "stop"]


def test_non_conforming_object_is_rejected_not_silently_accepted():
    """契约不一致的对象注册被拒绝（不静默接受、不降级为无操作）。"""
    reg = PluginRegistry()
    with pytest.raises(AttributeError):
        reg.register(object())  # 无 init/start/stop/kind/name
    assert reg.list_kind(PluginKind.MODEL) == []


def test_plugin_protocol_is_the_single_contract():
    """`Plugin` 协议是唯一契约；探针实现须满足该协议。"""
    assert isinstance(_Probe(PluginKind.MODEL, "m"), Plugin)
    assert not isinstance(object(), Plugin)
