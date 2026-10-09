"""记忆服务插件契约（APP-MEMORY）。"""

from __future__ import annotations

from asterism.plugins.kernel.base import Plugin, PluginKind


class MemoryProvider(Plugin):
    """记忆读写插件契约（kind = MEMORY）。"""

    kind = PluginKind.MEMORY
    name = "base"

    def store(self, key: str, value: str) -> None:
        """写入记忆。"""
        raise NotImplementedError

    def read(self, key: str) -> str | None:
        """读取记忆。"""
        raise NotImplementedError
