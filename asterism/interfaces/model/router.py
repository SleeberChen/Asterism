"""模型供应路由（FastAPI）。

职责：注入隔离上下文 → 调用用例 → 映射 ``AsterismError`` 为统一错误响应。
对外响应只含 ``AST-ERR`` 错误码 + 用户可读信息 + 链路标识，不泄露堆栈 / SQL / 内网地址（TC-16）。

隔离上下文注入复用 `APP-COMPLIANCE` 提供的统一入口 ``resolve_tenant_context``
（各应用不各自实现，防口径漂移；见 P3 §5 单写者表）。
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, StreamingResponse

from asterism.application.model.use_case import ModelInvokeUseCase
from asterism.interfaces.compliance.deps import resolve_tenant_context
from asterism.seedwork.context import TenantContext, reset_tenant_context, set_tenant_context
from asterism.seedwork.exceptions import AsterismError
from .schemas import ModelChunkResponse, ModelInvokeRequest, ModelInvokeResponse, ModelStreamRequest

router = APIRouter(prefix="/api/v1/models", tags=["models"])


@router.post("/invoke")
async def model_invoke(
    request: Request,
    body: ModelInvokeRequest,
    tenant: TenantContext = Depends(resolve_tenant_context),
) -> ModelInvokeResponse:
    token = set_tenant_context(tenant)  # 框架统一注入隔离上下文（TC-12）
    try:
        use_case: ModelInvokeUseCase = request.app.state.model_use_case
        resp = await use_case.execute(
            body.prompt,
            request_id=tenant.request_id,
            model=body.model,
            max_tokens=body.max_tokens,
        )
        return ModelInvokeResponse(
            text=resp.text,
            tenant_id=resp.tenant_id,
            model=resp.model,
            request_id=resp.request_id,
        )
    except AsterismError as exc:
        return JSONResponse(status_code=exc.http_status, content=exc.to_dict())
    finally:
        reset_tenant_context(token)  # 避免上下文泄漏到下一请求


@router.post("/invoke/stream")
async def model_invoke_stream(
    request: Request,
    body: ModelStreamRequest,
    tenant: TenantContext = Depends(resolve_tenant_context),
) -> StreamingResponse:
    """流式调用：以 SSE（``text/event-stream``）逐帧推送 ``ModelChunkResponse``。

    隔离上下文的 set / reset **必须成对出现在同一个 Context 内**：流式响应体由 starlette
    交给独立 task 迭代（其 context 是入口 context 的副本），若在入口函数 set、在生成器里
    reset，会触发 ``ValueError: Token was created in a different Context``。
    故此处把注入与复位一并下沉到生成器内部（TC-12 注入语义不变）。

    流式过程中的错误以 SSE ``event: error`` 帧推送统一错误体，不泄露内部细节（TC-16）。
    """
    use_case: ModelInvokeUseCase = request.app.state.model_use_case

    async def event_gen():
        # 与 finally 中的 reset 同处生成器 context，确保 token 成对生效（TC-12）
        token = set_tenant_context(tenant)
        try:
            async for chunk in use_case.execute_stream(
                body.prompt,
                request_id=tenant.request_id,
                model=body.model,
                max_tokens=body.max_tokens,
                vendor_id=body.vendor_id,
                template_id=body.template_id,
                var_map=body.var_map,
            ):
                chunk.request_id = chunk.request_id or tenant.request_id
                payload = ModelChunkResponse(
                    content=chunk.content,
                    tenant_id=chunk.tenant_id,
                    model=chunk.model,
                    request_id=chunk.request_id,
                    finished=chunk.finished,
                )
                yield f"data: {payload.model_dump_json(exclude_none=True)}\n\n"
        except AsterismError as exc:
            # 流式错误帧：统一错误体（AST-ERR 码 + 用户可读信息 + 链路标识），不泄露堆栈
            yield f"event: error\ndata: {json.dumps(exc.to_dict(), ensure_ascii=False)}\n\n"
        finally:
            # 生成器运行在流式 task 的 context（入口 context 的副本）中，随 task 结束即丢弃。
            # 若生成器被提前 aclose 于另一 context，该 token 不可复位（ValueError）；
            # 此时副本已弃用、不构成泄漏，故显式忽略这一收尾竞态（非业务异常，不吞错误）。
            try:
                reset_tenant_context(token)
            except ValueError:
                pass

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )
