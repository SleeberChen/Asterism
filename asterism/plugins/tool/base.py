"""工具接入插件契约（APP-TOOL）。"""

from __future__ import annotations

from typing import Any

from asterism.plugins.kernel.base import Plugin, PluginKind


class ToolProvider(Plugin):
    """工具调用插件契约（kind = MODEL_以外，独立种类）。"""

    kind = PluginKind.TOOL
    name = "base"

    def invoke(self, tool_name: str, args: dict, **kwargs: Any) -> Any:
        """调用工具，返回结果。"""
        raise NotImplementedError
