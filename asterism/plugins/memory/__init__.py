"""记忆服务插件（APP-MEMORY）。会话级与短期记忆。不依赖其他三类（TC-11）。"""

from .base import MemoryProvider

__all__ = ["MemoryProvider"]
