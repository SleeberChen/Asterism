"""模型调用用例（应用层门面，全链路异步）。

原路径：直接 prompt → 端口调用。
结构化路径（vendor_repo / template_repo 由组合根注入）：经 DB 仓储解析厂商 / 模型 / 模板，
由 ``UnifiedModelInvocationService`` 渲染模板并调用端口（callLLM 不进实体，DMP-19 待登记）。
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Optional

from asterism.domain.model.model import ModelChunk, ModelRequest, ModelResponse
from asterism.domain.model.ports import ModelPort
from asterism.domain.model.catalog import (
    InvariantViolationError,
    NotFoundError as ModelNotFound,
)
from asterism.domain.model.repository import VendorRepository, PromptTemplateRepository
from asterism.domain.model.service import UnifiedModelInvocationService
from asterism.seedwork.context import require_tenant_context
from asterism.seedwork.exceptions import (
    AsterismError,
    BusinessError,
    ExternalDependencyError,
    SystemError,
)


class ModelInvokeUseCase:
    """执行一次模型调用：参数校验 → 注入隔离上下文 → 端口调用（异步）→ 错误映射。"""

    def __init__(
        self,
        port: ModelPort,
        vendor_repo: Optional[VendorRepository] = None,
        template_repo: Optional[PromptTemplateRepository] = None,
    ) -> None:
        self._port = port
        self._vendor_repo = vendor_repo
        self._template_repo = template_repo

    async def execute(
        self,
        prompt: Optional[str] = None,
        *,
        request_id: Optional[str] = None,
        model: str = "default",
        max_tokens: int = 2048,
        vendor_id: Optional[str] = None,
        template_id: Optional[str] = None,
        var_map: Optional[dict[str, str]] = None,
    ) -> ModelResponse:
        # 隔离上下文缺失即拒绝（TC-12：框架统一注入；缺失抛 AST-ERR-2004）
        ctx = require_tenant_context()

        # 结构化路径：经真实持久化仓储解析（vendor_repo/template_repo 由组合根注入）
        if (
            self._vendor_repo is not None
            and self._template_repo is not None
            and (vendor_id or template_id)
        ):
            return await self._execute_structured(
                ctx,
                model=model,
                max_tokens=max_tokens,
                vendor_id=vendor_id,
                template_id=template_id,
                var_map=var_map,
                request_id=request_id,
            )

        # 原路径：直接 prompt
        if not prompt or not prompt.strip():
            raise BusinessError("AST-ERR-3001", message="提示词不能为空")

        req = ModelRequest(
            tenant_id=ctx.tenant_id, prompt=prompt, model=model, max_tokens=max_tokens
        )
        try:
            resp = await self._port.complete(req)
        except ExternalDependencyError:
            raise  # 4xx 透传（模型不可用 / 超时，AST-ERR-4001/4002）
        except AsterismError:
            raise  # 已映射错误直接透传
        except Exception as exc:  # 意外：包装为内部错误，保留因果链，不吞（TC-15）
            raise SystemError("AST-ERR-5001", request_id=request_id, cause=exc) from exc

        resp.request_id = request_id or ctx.request_id
        return resp

    async def _execute_structured(
        self,
        ctx,
        *,
        model: str,
        max_tokens: int,
        vendor_id: Optional[str],
        template_id: Optional[str],
        var_map: Optional[dict[str, str]],
        request_id: Optional[str],
    ) -> ModelResponse:
        svc = UnifiedModelInvocationService(self._vendor_repo, self._template_repo, self._port)
        try:
            result = await svc.call(
                tenant_id=ctx.tenant_id,
                vendor_id=vendor_id or "",
                model_id=model,
                template_id=template_id,
                var_map=var_map,
                max_tokens=max_tokens,
            )
        except (InvariantViolationError, ModelNotFound) as exc:
            raise BusinessError("AST-ERR-3002", message=str(exc)) from exc
        except ExternalDependencyError:
            raise  # 模型不可用 / 超时透传
        except AsterismError:
            raise
        except Exception as exc:
            raise SystemError("AST-ERR-5001", request_id=request_id, cause=exc) from exc

        resp = ModelResponse(text=result.text, tenant_id=ctx.tenant_id, model=result.model)
        resp.request_id = request_id or ctx.request_id
        return resp

    async def execute_stream(
        self,
        prompt: Optional[str] = None,
        *,
        request_id: Optional[str] = None,
        model: str = "default",
        max_tokens: int = 2048,
        vendor_id: Optional[str] = None,
        template_id: Optional[str] = None,
        var_map: Optional[dict[str, str]] = None,
    ) -> AsyncIterator[ModelChunk]:
        """流式执行：与 ``execute`` 同校验与隔离注入，但逐片 yield ``ModelChunk``。

        - 结构化路径经 ``UnifiedModelInvocationService.call_stream``（DB 解析 + 模板渲染 + 端口流）；
        - 原路径直连端口流；
        - 末帧 ``finished=True`` 由端口保证；错误映射与 ``execute`` 一致（4xx 透传、意外包 SystemError）。
        """
        ctx = require_tenant_context()

        # 结构化路径：经真实持久化仓储解析（vendor_repo/template_repo 由组合根注入）
        if (
            self._vendor_repo is not None
            and self._template_repo is not None
            and (vendor_id or template_id)
        ):
            svc = UnifiedModelInvocationService(self._vendor_repo, self._template_repo, self._port)
            try:
                async for chunk in svc.call_stream(
                    tenant_id=ctx.tenant_id,
                    vendor_id=vendor_id or "",
                    model_id=model,
                    template_id=template_id,
                    var_map=var_map,
                    max_tokens=max_tokens,
                ):
                    chunk.request_id = chunk.request_id or request_id or ctx.request_id
                    yield chunk
            except (InvariantViolationError, ModelNotFound) as exc:
                raise BusinessError("AST-ERR-3002", message=str(exc)) from exc
            except ExternalDependencyError:
                raise  # 模型不可用 / 超时透传
            except AsterismError:
                raise
            except Exception as exc:
                raise SystemError("AST-ERR-5001", request_id=request_id, cause=exc) from exc
            return

        # 原路径：直接 prompt
        if not prompt or not prompt.strip():
            raise BusinessError("AST-ERR-3001", message="提示词不能为空")

        req = ModelRequest(
            tenant_id=ctx.tenant_id, prompt=prompt, model=model, max_tokens=max_tokens
        )
        try:
            # 探测可选流式能力：无则回退为单次完整生成（单帧 finished），保持 SSE 契约
            streamer = getattr(self._port, "complete_stream", None)
            if streamer is not None:
                async for chunk in streamer(req):
                    chunk.request_id = chunk.request_id or request_id or ctx.request_id
                    yield chunk
                return
            resp = await self._port.complete(req)
            yield ModelChunk(
                content=resp.text,
                tenant_id=resp.tenant_id,
                model=resp.model,
                request_id=request_id or ctx.request_id,
                finished=True,
            )
        except ExternalDependencyError:
            raise  # 4xx 透传（模型不可用 / 超时，AST-ERR-4001/4002）
        except AsterismError:
            raise  # 已映射错误直接透传
        except Exception as exc:  # 意外：包装为内部错误，保留因果链，不吞（TC-15）
            raise SystemError("AST-ERR-5001", request_id=request_id, cause=exc) from exc
