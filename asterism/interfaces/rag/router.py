"""RAG 路由（FastAPI）。

职责：注入隔离上下文 → 调用用例 → 返回统一响应信封。
成功响应返回 ``ApiResult[QueryResponse]`` / ``ApiResult[IngestResponse]``（强制规范）；
所有失败由全局异常处理器（``asterism/main.py``）统一映射为 ``ApiResult.fail(...)`` 信封，
路由内不手写 ``JSONResponse(exc.to_dict())``。

隔离上下文注入复用 ``APP-COMPLIANCE`` 提供的统一入口 ``resolve_tenant_context``：
各应用不各自实现注入逻辑，防重复实现与口径漂移（P3 §5 单写者表）。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from asterism.application.rag.use_case import RagIngestUseCase, RagQueryUseCase
from asterism.interfaces.common.result import ApiResult
from asterism.interfaces.compliance.deps import resolve_tenant_context
from asterism.seedwork.context import TenantContext, reset_tenant_context, set_tenant_context

from .schemas import IngestRequest, IngestResponse, QueryRequest, QueryResponse, SourceRefOut

router = APIRouter(prefix="/api/v1/rag", tags=["rag"])


@router.post("/query", response_model=ApiResult[QueryResponse])
async def rag_query(
    request: Request,
    body: QueryRequest,
    tenant: TenantContext = Depends(resolve_tenant_context),
) -> ApiResult[QueryResponse]:
    token = set_tenant_context(tenant)  # 框架统一注入隔离上下文（TC-12）
    try:
        use_case: RagQueryUseCase = request.app.state.rag_use_case
        answer = use_case.execute(body.query, request_id=tenant.request_id, top_k=body.top_k)
        return ApiResult.ok(
            QueryResponse(
                answer=answer.text,
                sources=[
                    SourceRefOut(doc_id=s.doc_id, chunk_id=s.chunk_id, snippet=s.snippet)
                    for s in answer.sources
                ],
                tenant_id=answer.tenant_id,
                request_id=answer.request_id,
            ),
            request_id=tenant.request_id,
        )
    finally:
        reset_tenant_context(token)  # 避免上下文泄漏到下一请求


@router.post("/ingest", response_model=ApiResult[IngestResponse])
async def rag_ingest(
    request: Request,
    body: IngestRequest,
    tenant: TenantContext = Depends(resolve_tenant_context),
) -> ApiResult[IngestResponse]:
    token = set_tenant_context(tenant)  # 框架统一注入隔离上下文（TC-12）
    try:
        use_case: RagIngestUseCase = request.app.state.rag_ingest_use_case
        doc_id, chunk_count = use_case.execute(
            title=body.title, content=body.content, doc_id=body.doc_id
        )
        return ApiResult.ok(
            IngestResponse(
                tenant_id=tenant.tenant_id,
                doc_id=doc_id,
                chunk_count=chunk_count,
            ),
            request_id=tenant.request_id,
        )
    finally:
        reset_tenant_context(token)  # 避免上下文泄漏到下一请求
