"""硅基流动供应商适配器（``ModelProvider`` 插件 → 领域 ``ModelPort``）。

将领域 ``ModelRequest`` 适配为 SiliconFlow OpenAI 兼容调用，并把生成结果包装为
``ModelResponse``；供应商内部异常已在插件层映射为 ``ExternalDependencyError``，此处不重复包装。

生产替换：与 ``StubModelAdapter`` 同地位，经协议注册表按 ``access_protocol`` 选择（见
``provider_registry``），业务编排不感知具体供应商。
"""
from __future__ import annotations

from asterism.domain.model.model import ModelRequest, ModelResponse
from asterism.domain.model.ports import ModelPort
from asterism.plugins.kernel.base import PluginKind
from asterism.plugins.model.siliconflow import SiliconFlowProvider


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
