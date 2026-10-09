"""插件注册表（内核层）。

单一注册点；模型 / 工具 / 技能 / 记忆四类插件经此注册与发现。
本模块不 import 任何具体插件包（TC-11）；仅依赖本包 ``base``。
"""

from __future__ import annotations

from typing import Dict, List, Optional

from .base import Plugin, PluginKind


class PluginRegistry:
    """进程内插件注册表。"""

    def __init__(self) -> None:
        # (kind, name) -> Plugin
        self._plugins: Dict[tuple[PluginKind, str], Plugin] = {}

    def register(self, plugin: Plugin) -> None:
        """注册插件（覆盖同名同种类）。"""
        plugin.init()
        self._plugins[(plugin.kind, plugin.name)] = plugin

    def get(self, kind: PluginKind, name: str) -> Optional[Plugin]:
        return self._plugins.get((kind, name))

    def list_kind(self, kind: PluginKind) -> List[Plugin]:
        return [p for (k, _), p in self._plugins.items() if k == kind]

    def start_all(self) -> None:
        for p in self._plugins.values():
            p.start()

    def stop_all(self) -> None:
        for p in self._plugins.values():
            p.stop()


_REGISTRY: Optional[PluginRegistry] = None


def get_registry() -> PluginRegistry:
    """返回进程级单例注册表（本期进程内单点，TC-18 已登记）。"""
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = PluginRegistry()
    return _REGISTRY
