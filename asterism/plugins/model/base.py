"""模型供应商插件契约（APP-MODEL）。"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from asterism.plugins.kernel.base import Plugin, PluginKind


class ModelProvider(Plugin):
    """模型生成插件契约。

    实现须声明 ``kind = PluginKind.MODEL``。``complete`` 为同步生成接口；
    非幂等（P5 §14.4.2：model 生成禁止自动重试，改走备用供应商）。
    ``complete_stream`` 为可选流式能力，默认不实现。
    """

    kind = PluginKind.MODEL
    name = "base"

    def complete(self, prompt: str, **kwargs: Any) -> str:
        """给定提示词，返回生成文本。"""
        raise NotImplementedError

    async def complete_stream(self, prompt: str, **kwargs: Any) -> AsyncIterator[str]:
        """流式生成（可选）。默认不实现；支持流的供应商重写此方法，逐片 yield 文本片段。"""
        raise NotImplementedError
