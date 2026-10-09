"""技能生命周期插件契约（APP-SKILL）。"""

from __future__ import annotations

from asterism.plugins.kernel.base import Plugin, PluginKind


class SkillProvider(Plugin):
    """技能加载 / 启停插件契约（kind = SKILL）。"""

    kind = PluginKind.SKILL
    name = "base"

    def load(self, source: str) -> None:
        """从已登记来源加载技能（来源须通过白名单校验 TC-24）。"""
        raise NotImplementedError

    def unload(self) -> None:
        """卸载技能。"""
        raise NotImplementedError
