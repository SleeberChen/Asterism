"""插件区（APP-PLUGIN 内核 + 四类插件）。

一切皆插件（P3 CON04 / P5 TC-11）：模型 / 工具 / 技能 / 记忆四类能力统一经内核注册与
生命周期管理。依赖铁律（TC-11）：
- 内核（``plugins.kernel``）禁止反向 import 四类插件包；
- 四类插件（model/tool/skill/memory）互不依赖（出边数 = 0）。
"""

from .kernel.base import Plugin, PluginKind
from .kernel.registry import PluginRegistry, get_registry

__all__ = ["Plugin", "PluginKind", "PluginRegistry", "get_registry"]
