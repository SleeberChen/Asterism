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
