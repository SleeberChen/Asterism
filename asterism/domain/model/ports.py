"""模型供应端口（领域层定义，基础设施/插件实现；依赖倒置 TC-09）。"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from .model import ModelRequest, ModelResponse


@runtime_checkable
class ModelPort(Protocol):
    """模型供应端口：按请求返回生成结果（实现须经插件内核注册，TC-11）。"""

    def complete(self, request: ModelRequest) -> ModelResponse:
        ...
