"""技能生命周期插件（APP-SKILL）。来源须白名单校验（TC-24 / M8）。不依赖其他三类（TC-11）。"""

from .base import SkillProvider

__all__ = ["SkillProvider"]
