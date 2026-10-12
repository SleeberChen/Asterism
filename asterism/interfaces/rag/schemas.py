"""RAG 接口层请求 / 响应 Schema（Pydantic v2）。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=4000, description="用户查询文本")
    top_k: int = Field(4, ge=1, le=20, description="召回片段数")


class SourceRefOut(BaseModel):
    doc_id: str
    chunk_id: str
    snippet: str


class QueryResponse(BaseModel):
    answer: str
    sources: list[SourceRefOut]
    tenant_id: str
    request_id: str | None = None


class IngestRequest(BaseModel):
    """知识库入库请求（文本 / Markdown）。"""

    title: str = Field(..., min_length=1, max_length=200, description="文档标题")
    content: str = Field(
        ..., min_length=1, max_length=100_000, description="文档正文（文本 / Markdown）"
    )
    doc_id: str | None = Field(
        default=None, description="可选外部文档 ID；缺省由服务端生成（幂等 upsert 依据）"
    )


class IngestResponse(BaseModel):
    """知识库入库响应。"""

    tenant_id: str
    doc_id: str
    chunk_count: int = Field(..., description="本次入库切片数")
