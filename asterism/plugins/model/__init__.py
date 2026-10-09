"""模型供应商插件（APP-MODEL）。

实现经 ``plugins.kernel`` 注册；本包不依赖 tool/skill/memory（TC-11）。
真实供应商（OpenAI / Anthropic / 本地模型等）以后作为本包下的具体插件实现，
经统一 ``ModelProvider`` 契约接入，业务编排不感知具体供应商（P5 ADR-008 回退策略）。
"""

from .base import ModelProvider
from .stub import StubModelProvider

__all__ = ["ModelProvider", "StubModelProvider"]
