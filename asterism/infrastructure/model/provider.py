"""模型供应适配器（演示用，实现 ModelPort）。

将插件桩模型（``plugins.model.StubModelProvider``）适配为领域模型端口，并演示：
- 模型供应商经插件内核注册（TC-11）；
- 生成失败映射为外部依赖错误（AST-ERR-4001），由上层决定回退（ADR-008）；
- 不使用真实密钥 / 网络（TC-01）。

生产替换：新增 ``plugins.model.<vendor>`` 实现 ``ModelProvider`` 并经内核注册，
业务编排不感知具体供应商。
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from asterism.domain.model.model import ModelChunk, ModelRequest, ModelResponse
from asterism.domain.model.ports import ModelPort
from asterism.plugins.kernel.base import PluginKind
from asterism.plugins.model.stub import StubModelProvider
from asterism.seedwork.exceptions import ExternalDependencyError


class StubModelAdapter(ModelPort):
    def __init__(self) -> None:
        self._stub = StubModelProvider()
        self._stub.kind = PluginKind.MODEL  # 视为已注册的模型插件

    async def complete(self, request: ModelRequest) -> ModelResponse:
        try:
            text = self._stub.complete(request.prompt)
        except Exception as exc:
            # 模型供应商不可用且回退失败：返回显式错误，禁止编造内容（AST-ERR-4001）
            raise ExternalDependencyError(
                "AST-ERR-4001", message="模型生成失败", cause=exc
            ) from exc
        return ModelResponse(text=text, tenant_id=request.tenant_id, model=request.model)

    async def complete_stream(self, request: ModelRequest) -> AsyncIterator[ModelChunk]:
        """流式适配：将插件逐片文本包装为领域 ``ModelChunk``；失败时映射为外部依赖错误。

        采用「预读一帧」策略标记末帧 ``finished=True``：非末帧先缓存、确认有后续才发出，
        循环结束时把最后一帧以 ``finished=True`` 发出；空流则发一帧空内容末帧以宣告完成。
        """
        try:
            gen = self._stub.complete_stream(request.prompt)
            prev: Optional[str] = None
            async for piece in gen:
                if prev is not None:
                    yield ModelChunk(content=prev, tenant_id=request.tenant_id, model=request.model)
                prev = piece
            if prev is not None:
                yield ModelChunk(content=prev, tenant_id=request.tenant_id, model=request.model, finished=True)
            else:
                yield ModelChunk(content="", tenant_id=request.tenant_id, model=request.model, finished=True)
        except ExternalDependencyError:
            raise  # 4xx 透传（模型不可用 / 超时，AST-ERR-4001/4002）
        except Exception as exc:
            # 模型供应商不可用且回退失败：返回显式错误，禁止编造内容（AST-ERR-4001）
            raise ExternalDependencyError(
                "AST-ERR-4001", message="模型流式生成失败", cause=exc
            ) from exc
