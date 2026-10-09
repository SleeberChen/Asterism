"""插件内核（APP-PLUGIN 共享内核）。

零业务依赖；仅定义注册 / 生命周期接口与插件契约。禁止 import 任何具体插件包（TC-11）。
"""

from .base import Plugin, PluginKind
from .registry import PluginRegistry, get_registry

__all__ = ["Plugin", "PluginKind", "PluginRegistry", "get_registry"]
