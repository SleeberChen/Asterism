"""模型供应路由（FastAPI）。

职责：注入隔离上下文 → 调用用例 → 返回统一响应信封。
成功响应一律返回 ``ApiResult[<业务 Schema>]``（强制规范）；所有失败由全局异常处理器
（``asterism/main.py``）统一映射为 ``ApiResult.fail(...)`` 信封，路由内不手写
``JSONResponse(exc.to_dict())``。流式（SSE）成功帧为 ``ApiResult[ModelChunkResponse]``，
错误帧为 ``ApiResult.fail(...)``（``event: error``），与 JSON 接口同信封。

隔离上下文注入复用 `APP-COMPLIANCE` 提供的统一入口 ``resolve_tenant_context``
（各应用不各自实现，防口径漂移；见 P3 §5 单写者表）。
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import StreamingResponse

from asterism.application.model.management_use_case import ModelManagementUseCase
from asterism.application.model.use_case import ModelInvokeUseCase
from asterism.domain.model.catalog import ModelCapability, ModelSpec, VendorConfig
from asterism.infrastructure.persistence.db import new_session
from asterism.infrastructure.persistence.engine import get_business_engine
from asterism.infrastructure.persistence.model_repository import SqlVendorRepository
from asterism.interfaces.common.result import ApiResult
from asterism.interfaces.compliance.deps import resolve_tenant_context
from asterism.interfaces.model.management_schemas import (
    ModelRegisterRequest,
    ModelResponse,
    VendorConnectionRequest,
    VendorCredentialRequest,
    VendorRegisterRequest,
    VendorResponse,
    VendorStatusRequest,
    to_model_response,
    to_vendor_response,
)
from asterism.seedwork.context import TenantContext, reset_tenant_context, set_tenant_context
from asterism.seedwork.exceptions import AsterismError
from .schemas import ModelChunkResponse, ModelInvokeRequest, ModelInvokeResponse, ModelStreamRequest

router = APIRouter(prefix="/api/v1/models", tags=["models"])


@router.post("/invoke", response_model=ApiResult[ModelInvokeResponse])
async def model_invoke(
    request: Request,
    body: ModelInvokeRequest,
    tenant: TenantContext = Depends(resolve_tenant_context),
) -> ApiResult[ModelInvokeResponse]:
    token = set_tenant_context(tenant)  # 框架统一注入隔离上下文（TC-12）
    try:
        use_case: ModelInvokeUseCase = request.app.state.model_use_case
        resp = await use_case.execute(
            body.prompt,
            request_id=tenant.request_id,
            model=body.model,
            max_tokens=body.max_tokens,
        )
        return ApiResult.ok(
            ModelInvokeResponse(
                text=resp.text,
                tenant_id=resp.tenant_id,
                model=resp.model,
                request_id=resp.request_id,
            )
        )
    finally:
        reset_tenant_context(token)  # 避免上下文泄漏到下一请求


@router.post("/invoke/stream")
async def model_invoke_stream(
    request: Request,
    body: ModelStreamRequest,
    tenant: TenantContext = Depends(resolve_tenant_context),
) -> StreamingResponse:
    """流式调用：以 SSE（``text/event-stream``）逐帧推送 ``ApiResult[ModelChunkResponse]``。

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
                # 成功帧统一包裹为 ApiResult[ModelChunkResponse]（强制规范）
                yield f"data: {ApiResult.ok(payload, request_id=tenant.request_id).model_dump_json(exclude_none=True)}\n\n"
        except AsterismError as exc:
            # 流式错误帧：统一信封（AST-ERR 码 + 用户可读信息 + 链路标识），不泄露堆栈
            yield (
                f"event: error\n"
                f"data: {json.dumps(ApiResult.fail(code=exc.code, message=exc.message, request_id=exc.request_id).model_dump(), ensure_ascii=False)}\n\n"
            )
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


# ---------------------------------------------------------------------------
# 厂商全量 CRUD（接口 → 业务库；隔离上下文由框架注入，TC-12）
# 每条端点内 set/reset 隔离上下文（非流式，同 context 内成对，无跨 Context 陷阱）；
# 业务异常由全局 handler 统一映射 AST-ERR 信封（TC-16 不泄露堆栈）；其余经全局 handler 兜底。
# ---------------------------------------------------------------------------
async def get_vendor_repo(request: Request) -> AsyncIterator[SqlVendorRepository]:
    """Per-request 业务库异步会话 → 厂商仓储（会话随请求结束关闭，连接不泄漏）。"""
    engine = await get_business_engine()
    async with new_session(engine) as session:
        yield SqlVendorRepository(session)


@router.post("/vendors", response_model=ApiResult[VendorResponse], status_code=201)
async def create_vendor(
    body: VendorRegisterRequest,
    request: Request,
    tenant: TenantContext = Depends(resolve_tenant_context),
    repo: SqlVendorRepository = Depends(get_vendor_repo),
) -> ApiResult[VendorResponse]:
    token = set_tenant_context(tenant)
    try:
        uc = ModelManagementUseCase(repo)
        v = await uc.register_vendor(
            vendor_id=body.vendor_id,
            plugin_registration_ref=body.plugin_registration_ref,
            name=body.name,
            config=VendorConfig(
                access_protocol=body.access_protocol,
                base_url=body.base_url,
                credential_handle=body.credential_handle,
                default_timeout_budget_ms=body.default_timeout_budget_ms,
            ),
        )
        return ApiResult.ok(to_vendor_response(v))
    finally:
        reset_tenant_context(token)


@router.post("/vendors/{vendor_id}/models", response_model=ApiResult[ModelResponse], status_code=201)
async def create_model(
    vendor_id: str,
    body: ModelRegisterRequest,
    request: Request,
    tenant: TenantContext = Depends(resolve_tenant_context),
    repo: SqlVendorRepository = Depends(get_vendor_repo),
) -> ApiResult[ModelResponse]:
    token = set_tenant_context(tenant)
    try:
        uc = ModelManagementUseCase(repo)
        m = await uc.register_model(
            vendor_id=vendor_id,
            spec=ModelSpec(
                model_id=body.model_id,
                name=body.name,
                capability=ModelCapability(
                    context_window=body.context_window,
                    modalities=tuple(body.modalities),
                    pricing_note=body.pricing_note,
                ),
                is_default=body.is_default,
            ),
        )
        return ApiResult.ok(to_model_response(m, vendor_id))
    finally:
        reset_tenant_context(token)


@router.get("/vendors", response_model=ApiResult[list[VendorResponse]])
async def list_vendors(
    request: Request,
    tenant: TenantContext = Depends(resolve_tenant_context),
    repo: SqlVendorRepository = Depends(get_vendor_repo),
) -> ApiResult[list[VendorResponse]]:
    token = set_tenant_context(tenant)
    try:
        vendors = await ModelManagementUseCase(repo).list_vendors()
        return ApiResult.ok([to_vendor_response(v) for v in vendors])
    finally:
        reset_tenant_context(token)


@router.get("/vendors/{vendor_id}", response_model=ApiResult[VendorResponse])
async def get_vendor(
    vendor_id: str,
    request: Request,
    tenant: TenantContext = Depends(resolve_tenant_context),
    repo: SqlVendorRepository = Depends(get_vendor_repo),
) -> ApiResult[VendorResponse]:
    token = set_tenant_context(tenant)
    try:
        v = await ModelManagementUseCase(repo).get_vendor(vendor_id=vendor_id)
        return ApiResult.ok(to_vendor_response(v))
    finally:
        reset_tenant_context(token)


@router.get("/vendors/{vendor_id}/models", response_model=ApiResult[list[ModelResponse]])
async def list_models(
    vendor_id: str,
    request: Request,
    tenant: TenantContext = Depends(resolve_tenant_context),
    repo: SqlVendorRepository = Depends(get_vendor_repo),
) -> ApiResult[list[ModelResponse]]:
    token = set_tenant_context(tenant)
    try:
        models = await ModelManagementUseCase(repo).list_models(vendor_id=vendor_id)
        return ApiResult.ok([to_model_response(m, vendor_id) for m in models])
    finally:
        reset_tenant_context(token)


@router.put("/vendors/{vendor_id}/status", response_model=ApiResult[VendorResponse])
async def set_vendor_status(
    vendor_id: str,
    body: VendorStatusRequest,
    request: Request,
    tenant: TenantContext = Depends(resolve_tenant_context),
    repo: SqlVendorRepository = Depends(get_vendor_repo),
) -> ApiResult[VendorResponse]:
    token = set_tenant_context(tenant)
    try:
        v = await ModelManagementUseCase(repo).set_vendor_status(
            vendor_id=vendor_id, status=body.status, expected_version=body.expected_version
        )
        return ApiResult.ok(to_vendor_response(v))
    finally:
        reset_tenant_context(token)


# ---------------------------------------------------------------------------
# 供应商 API 管理：凭据轮换 / 连接配置更新（两者均走乐观锁，冲突映射 409）
# 写操作仍嵌套在厂商之下；凭据与连接配置互为独立子资源，便于分别轮换与审计。
# ---------------------------------------------------------------------------
@router.post("/vendors/{vendor_id}/credentials", response_model=ApiResult[VendorResponse])
async def rotate_vendor_credentials(
    vendor_id: str,
    body: VendorCredentialRequest,
    request: Request,
    tenant: TenantContext = Depends(resolve_tenant_context),
    repo: SqlVendorRepository = Depends(get_vendor_repo),
) -> ApiResult[VendorResponse]:
    token = set_tenant_context(tenant)
    try:
        v = await ModelManagementUseCase(repo).rotate_vendor_credentials(
            vendor_id=vendor_id,
            new_credential_handle=body.new_credential_handle,
            expected_version=body.expected_version,
        )
        return ApiResult.ok(to_vendor_response(v))
    finally:
        reset_tenant_context(token)


@router.post("/vendors/{vendor_id}/connection", response_model=ApiResult[VendorResponse])
async def update_vendor_connection(
    vendor_id: str,
    body: VendorConnectionRequest,
    request: Request,
    tenant: TenantContext = Depends(resolve_tenant_context),
    repo: SqlVendorRepository = Depends(get_vendor_repo),
) -> ApiResult[VendorResponse]:
    token = set_tenant_context(tenant)
    try:
        v = await ModelManagementUseCase(repo).update_vendor_connection(
            vendor_id=vendor_id,
            access_protocol=body.access_protocol,
            base_url=body.base_url,
            default_timeout_budget_ms=body.default_timeout_budget_ms,
            expected_version=body.expected_version,
        )
        return ApiResult.ok(to_vendor_response(v))
    finally:
        reset_tenant_context(token)


@router.delete("/vendors/{vendor_id}", status_code=204)
async def remove_vendor(
    vendor_id: str,
    request: Request,
    tenant: TenantContext = Depends(resolve_tenant_context),
    repo: SqlVendorRepository = Depends(get_vendor_repo),
) -> Response:
    # 204 No Content：按强制规范豁免包裹（无响应体）
    token = set_tenant_context(tenant)
    try:
        await ModelManagementUseCase(repo).delete_vendor(vendor_id=vendor_id)
        return Response(status_code=204)
    finally:
        reset_tenant_context(token)


@router.delete("/vendors/{vendor_id}/models/{model_id}", status_code=204)
async def remove_model(
    vendor_id: str,
    model_id: str,
    request: Request,
    tenant: TenantContext = Depends(resolve_tenant_context),
    repo: SqlVendorRepository = Depends(get_vendor_repo),
) -> Response:
    # 204 No Content：按强制规范豁免包裹（无响应体）
    token = set_tenant_context(tenant)
    try:
        await ModelManagementUseCase(repo).delete_model(vendor_id=vendor_id, model_id=model_id)
        return Response(status_code=204)
    finally:
        reset_tenant_context(token)


# ---------------------------------------------------------------------------
# 顶层跨厂商模型查询（只读；写操作仍走嵌套端点 /vendors/{id}/models）。
# 置于文件末尾：确保 /vendors 等静态路由优先注册，避免被 /{model_id} 参数路由吞掉。
# 返回携带 vendor_id，便于调用方定位模型归属厂商。
# ---------------------------------------------------------------------------
@router.get("", response_model=ApiResult[list[ModelResponse]])
async def list_all_models(
    request: Request,
    tenant: TenantContext = Depends(resolve_tenant_context),
    repo: SqlVendorRepository = Depends(get_vendor_repo),
) -> ApiResult[list[ModelResponse]]:
    token = set_tenant_context(tenant)
    try:
        rows = await ModelManagementUseCase(repo).list_all_models()
        return ApiResult.ok([to_model_response(m, vid) for vid, m in rows])
    finally:
        reset_tenant_context(token)


@router.get("/{model_id}", response_model=ApiResult[ModelResponse])
async def get_model_by_id(
    model_id: str,
    request: Request,
    tenant: TenantContext = Depends(resolve_tenant_context),
    repo: SqlVendorRepository = Depends(get_vendor_repo),
) -> ApiResult[ModelResponse]:
    token = set_tenant_context(tenant)
    try:
        vid, m = await ModelManagementUseCase(repo).get_model(model_id=model_id)
        return ApiResult.ok(to_model_response(m, vid))
    finally:
        reset_tenant_context(token)
