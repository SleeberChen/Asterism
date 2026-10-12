"""硅基流动供应商适配器（``ModelProvider`` 插件 → 领域 ``ModelPort``）。

将领域 ``ModelRequest`` 适配为 SiliconFlow OpenAI 兼容调用，并把生成结果包装为
``ModelResponse``；供应商内部异常已在插件层映射为 ``ExternalDependencyError``，此处不重复包装。

生产替换：与 ``StubModelAdapter`` 同地位，经协议注册表按 ``access_protocol`` 选择（见
``provider_registry``），业务编排不感知具体供应商。
"""
from __future__ import annotations

from collections.abc import AsyncIterator

from asterism.domain.model.model import ModelChunk, ModelRequest, ModelResponse
from asterism.domain.model.ports import ModelPort
from asterism.plugins.kernel.base import PluginKind
from asterism.plugins.model.siliconflow import SiliconFlowProvider
from asterism.seedwork.exceptions import ExternalDependencyError


class SiliconFlowAdapter(ModelPort):
    """硅基流动 OpenAI 兼容适配器。"""

    def __init__(self, *, base_url: str, api_key: str, timeout_s: float = 60.0) -> None:
        self._provider = SiliconFlowProvider()
        self._provider.kind = PluginKind.MODEL
        self._base_url = base_url
        self._api_key = api_key
        self._timeout = timeout_s

    async def complete(self, request: ModelRequest) -> ModelResponse:
        text = await self._provider.chat(
            api_key=self._api_key,
            base_url=self._base_url,
            model=request.model,
            prompt=request.prompt,
            max_tokens=request.max_tokens,
            timeout_s=self._timeout,
        )
        return ModelResponse(text=text, tenant_id=request.tenant_id, model=request.model)

    async def complete_stream(self, request: ModelRequest) -> AsyncIterator[ModelChunk]:
        """流式适配：将插件逐片文本包装为领域 ``ModelChunk``；失败时映射为外部依赖错误。

        采用「预读一帧」策略标记末帧 ``finished=True``（与 StubModelAdapter 一致）：
        非末帧先缓存、确认有后续才发出，循环结束时把最后一帧以 ``finished=True`` 发出；
        空流则发一帧空内容末帧以宣告完成。不缓冲完整响应，逐片产出、逐片映射，
        与缓冲模式 ``complete`` 语义一致（SSE 契约不变）。
        """
        try:
            gen = self._provider.complete_stream(
                request.prompt,
                api_key=self._api_key,
                base_url=self._base_url,
                model=request.model,
                max_tokens=request.max_tokens,
                timeout_s=self._timeout,
            )
            prev: str | None = None
            async for piece in gen:
                if prev is not None:
                    yield ModelChunk(content=prev, tenant_id=request.tenant_id, model=request.model)
                prev = piece
            if prev is not None:
                yield ModelChunk(
                    content=prev, tenant_id=request.tenant_id, model=request.model, finished=True
                )
            else:
                yield ModelChunk(
                    content="", tenant_id=request.tenant_id, model=request.model, finished=True
                )
        except ExternalDependencyError:
            raise  # 4xx 透传（模型不可用 / 超时，AST-ERR-4001/4002）
        except Exception as exc:
            # 模型供应商不可用且回退失败：返回显式错误，禁止编造内容（AST-ERR-4001）
            raise ExternalDependencyError(
                "AST-ERR-4001", message="模型流式生成失败", cause=exc
            ) from exc
