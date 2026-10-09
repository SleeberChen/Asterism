"""工具接入插件（APP-TOOL）。不依赖 model/skill/memory（TC-11）。"""

from .base import ToolProvider

__all__ = ["ToolProvider"]
