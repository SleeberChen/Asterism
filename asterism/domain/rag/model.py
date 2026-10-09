"""RAG 领域模型（纯数据，无 IO、无框架依赖）。

**分层建模规范**：领域层实体 / 值对象用 ``dataclass``（或普通类），
**不引入 Pydantic**，保持领域纯净（框架零依赖，P5 TC-10）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Chunk:
    """文档切片（携带租户隔离维度）。"""

    id: str
    doc_id: str
    tenant_id: str
    text: str
    embedding: Optional[List[float]] = None


@dataclass
class Document:
    """知识库文档。"""

    id: str
    tenant_id: str
    title: str
    content: str


@dataclass
class Query:
    """检索查询（隔离维度由框架注入，业务代码不手拼，TC-12）。"""

    tenant_id: str
    text: str
    top_k: int = 4
    max_context_tokens: int = 2000


@dataclass
class RetrievalResult:
    """单条检索结果。"""

    chunk: Chunk
    score: float


@dataclass
class SourceRef:
    """回答引用的来源片段。"""

    doc_id: str
    chunk_id: str
    snippet: str


@dataclass
class Answer:
    """生成回答。"""

    text: str
    tenant_id: str
    request_id: Optional[str]
    sources: List[SourceRef] = field(default_factory=list)
