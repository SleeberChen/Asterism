"""模型供应端口（领域层定义，基础设施/插件实现；依赖倒置 TC-09）。"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol, runtime_checkable

from .model import ModelChunk, ModelRequest, ModelResponse


@runtime_checkable
class ModelPort(Protocol):
    """模型供应端口：按请求返回生成结果（实现须经插件内核注册，TC-11）。

    仅要求 ``complete``（非流式）。流式能力见 ``StreamingModelPort``（可选实现），
    调用方经 ``hasattr(port, "complete_stream")`` 探测后回退到 ``complete``。
    """

    async def complete(self, request: ModelRequest) -> ModelResponse:
        ...


@runtime_checkable
class StreamingModelPort(ModelPort, Protocol):
    """可选流式能力端口：在 ``ModelPort`` 之上新增 ``complete_stream``。

    实现须同时提供 ``complete`` 与 ``complete_stream``。``StubModelAdapter`` 即满足。
    调用方用 ``isinstance(port, StreamingModelPort)`` 或 ``hasattr`` 探测后再走流式路径。
    """

    async def complete_stream(self, request: ModelRequest) -> AsyncIterator[ModelChunk]:
        """流式生成：逐片产出 ``ModelChunk``，末帧 ``finished=True``（可选实现）。"""
        ...
