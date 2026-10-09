"""模型供应适配器（演示用，实现 ModelPort）。

将插件桩模型（``plugins.model.StubModelProvider``）适配为领域模型端口，并演示：
- 模型供应商经插件内核注册（TC-11）；
- 生成失败映射为外部依赖错误（AST-ERR-4001），由上层决定回退（ADR-008）；
- 不使用真实密钥 / 网络（TC-01）。

生产替换：新增 ``plugins.model.<vendor>`` 实现 ``ModelProvider`` 并经内核注册，
业务编排不感知具体供应商。
"""

from __future__ import annotations

from asterism.domain.model.model import ModelRequest, ModelResponse
from asterism.domain.model.ports import ModelPort
from asterism.plugins.kernel.base import PluginKind
from asterism.plugins.model.stub import StubModelProvider
from asterism.seedwork.exceptions import ExternalDependencyError


class StubModelAdapter(ModelPort):
    def __init__(self) -> None:
        self._stub = StubModelProvider()
        self._stub.kind = PluginKind.MODEL  # 视为已注册的模型插件

    def complete(self, request: ModelRequest) -> ModelResponse:
        try:
            text = self._stub.complete(request.prompt)
        except Exception as exc:
            # 模型供应商不可用且回退失败：返回显式错误，禁止编造内容（AST-ERR-4001）
            raise ExternalDependencyError(
                "AST-ERR-4001", message="模型生成失败", cause=exc
            ) from exc
        return ModelResponse(text=text, tenant_id=request.tenant_id, model=request.model)
