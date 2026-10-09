"""插件契约与种类（内核层，零业务依赖）。

仅定义协议与枚举；不引用任何具体插件实现（TC-11：内核不反向依赖四类插件）。
"""

from __future__ import annotations

from enum import Enum
from typing import Protocol, runtime_checkable


class PluginKind(str, Enum):
    """插件种类（对应模型 / 工具 / 技能 / 记忆四能力）。"""

    MODEL = "model"
    TOOL = "tool"
    SKILL = "skill"
    MEMORY = "memory"


@runtime_checkable
class Plugin(Protocol):
    """插件统一契约。

    具体插件须声明 ``kind`` 与 ``name``，并实现生命周期方法。
    四类插件互不依赖（TC-11）：不得在此协议中引用其他种类的实现。
    """

    kind: PluginKind
    name: str

    def init(self) -> None:
        """加载 / 校验（仅一次）。"""
        ...

    def start(self) -> None:
        """启用（请求入口可调用）。"""
        ...

    def stop(self) -> None:
        """停用 / 释放资源。"""
        ...
