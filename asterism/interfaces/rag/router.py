"""RAG 路由（FastAPI）。

职责：注入隔离上下文 → 调用用例 → 映射 ``AsterismError`` 为统一错误响应。
对外响应只含 ``AST-ERR`` 错误码 + 用户可读信息 + 链路标识，不泄露堆栈 / SQL / 内网地址（TC-16）。

隔离上下文注入复用 `APP-COMPLIANCE` 提供的统一入口 ``resolve_tenant_context``：
各应用不各自实现注入逻辑，防重复实现与口径漂移（P3 §5 单写者表）。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from asterism.application.rag.use_case import RagQueryUseCase
from asterism.interfaces.compliance.deps import resolve_tenant_context
from asterism.seedwork.context import TenantContext, reset_tenant_context, set_tenant_context
from asterism.seedwork.exceptions import AsterismError
from .schemas import QueryRequest, QueryResponse, SourceRefOut

router = APIRouter(prefix="/api/v1/rag", tags=["rag"])


@router.post("/query")
async def rag_query(
    request: Request,
    body: QueryRequest,
    tenant: TenantContext = Depends(resolve_tenant_context),
) -> QueryResponse:
    token = set_tenant_context(tenant)  # 框架统一注入隔离上下文（TC-12）
    try:
        use_case: RagQueryUseCase = request.app.state.rag_use_case
        answer = use_case.execute(body.query, request_id=tenant.request_id, top_k=body.top_k)
        return QueryResponse(
            answer=answer.text,
            sources=[
                SourceRefOut(doc_id=s.doc_id, chunk_id=s.chunk_id, snippet=s.snippet)
                for s in answer.sources
            ],
            tenant_id=answer.tenant_id,
            request_id=answer.request_id,
        )
    except AsterismError as exc:
        # 统一错误响应：含 AST-ERR 错误码 + 链路标识，不泄露内部细节（TC-16）
        return JSONResponse(status_code=exc.http_status, content=exc.to_dict())
    finally:
        reset_tenant_context(token)  # 避免上下文泄漏到下一请求
