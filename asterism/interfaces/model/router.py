"""模型供应路由（FastAPI）。

职责：注入隔离上下文 → 调用用例 → 映射 ``AsterismError`` 为统一错误响应。
对外响应只含 ``AST-ERR`` 错误码 + 用户可读信息 + 链路标识，不泄露堆栈 / SQL / 内网地址（TC-16）。

隔离上下文注入复用 `APP-COMPLIANCE` 提供的统一入口 ``resolve_tenant_context``
（各应用不各自实现，防口径漂移；见 P3 §5 单写者表）。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from asterism.application.model.use_case import ModelInvokeUseCase
from asterism.interfaces.compliance.deps import resolve_tenant_context
from asterism.seedwork.context import TenantContext, reset_tenant_context, set_tenant_context
from asterism.seedwork.exceptions import AsterismError
from .schemas import ModelInvokeRequest, ModelInvokeResponse

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
        resp = use_case.execute(
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
