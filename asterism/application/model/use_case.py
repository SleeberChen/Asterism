"""模型调用用例（应用层门面）。"""

from __future__ import annotations

from typing import Optional

from asterism.domain.model.model import ModelRequest, ModelResponse
from asterism.domain.model.ports import ModelPort
from asterism.seedwork.context import require_tenant_context
from asterism.seedwork.exceptions import (
    AsterismError,
    BusinessError,
    ExternalDependencyError,
    SystemError,
)


class ModelInvokeUseCase:
    """执行一次模型调用：参数校验 → 注入隔离上下文 → 端口调用 → 错误映射。"""

    def __init__(self, port: ModelPort) -> None:
        self._port = port

    def execute(
        self,
        prompt: str,
        *,
        request_id: Optional[str] = None,
        model: str = "default",
        max_tokens: int = 2048,
    ) -> ModelResponse:
        # 隔离上下文缺失即拒绝（TC-12：框架统一注入；缺失抛 AST-ERR-2004）
        ctx = require_tenant_context()

        if not prompt or not prompt.strip():
            raise BusinessError("AST-ERR-3001", message="提示词不能为空")

        req = ModelRequest(
            tenant_id=ctx.tenant_id, prompt=prompt, model=model, max_tokens=max_tokens
        )
        try:
            resp = self._port.complete(req)
        except ExternalDependencyError:
            raise  # 4xxx 透传（模型不可用 / 超时，AST-ERR-4001/4002）
        except AsterismError:
            raise  # 已映射错误直接透传
        except Exception as exc:  # 意外：包装为内部错误，保留因果链，不吞（TC-15）
            raise SystemError("AST-ERR-5001", request_id=request_id, cause=exc) from exc

        resp.request_id = request_id or ctx.request_id
        return resp
