"""模型供应商插件契约（APP-MODEL）。"""

from __future__ import annotations

from typing import Any

from asterism.plugins.kernel.base import Plugin, PluginKind


class ModelProvider(Plugin):
    """模型生成插件契约。

    实现须声明 ``kind = PluginKind.MODEL``。``complete`` 为同步生成接口；
    非幂等（P5 §14.4.2：model 生成禁止自动重试，改走备用供应商）。
    """

    kind = PluginKind.MODEL
    name = "base"

    def complete(self, prompt: str, **kwargs: Any) -> str:
        """给定提示词，返回生成文本。"""
        raise NotImplementedError
