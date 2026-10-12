"""RAG 查询用例 + 入库用例（应用层门面）。"""

from __future__ import annotations

import uuid

from asterism.domain.rag.chunking import split_document
from asterism.domain.rag.model import Answer, Document, Query
from asterism.domain.rag.orchestrator import RagOrchestrator
from asterism.domain.rag.ports import VectorStorePort
from asterism.seedwork.context import require_tenant_context
from asterism.seedwork.exceptions import (
    AsterismError,
    BusinessError,
    ExternalDependencyError,
    SystemError,
)


class RagQueryUseCase:
    """执行一次 RAG 查询：参数校验 → 注入隔离上下文 → 编排 → 错误映射。"""

    def __init__(self, orchestrator: RagOrchestrator) -> None:
        self._orchestrator = orchestrator

    def execute(
        self, query_text: str, *, request_id: str | None = None, top_k: int = 4
    ) -> Answer:
        # 隔离上下文缺失即拒绝（TC-12：框架统一注入；缺失抛 AST-ERR-2004）
        ctx = require_tenant_context()

        if not query_text or not query_text.strip():
            raise BusinessError("AST-ERR-3001", message="查询内容不能为空")

        query = Query(tenant_id=ctx.tenant_id, text=query_text, top_k=top_k)
        try:
            answer = self._orchestrator.answer(query)
        except ExternalDependencyError:
            raise  # 4xxx 透传（模型不可用 / 超时，AST-ERR-4001/4002）
        except AsterismError:
            raise  # 已映射错误直接透传
        except Exception as exc:  # 意外：包装为内部错误，保留因果链，不吞（TC-15）
            raise SystemError("AST-ERR-5001", request_id=request_id, cause=exc) from exc

        # 链路标识回填（领域层不感知请求标识）
        answer.request_id = request_id or ctx.request_id
        return answer


class RagIngestUseCase:
    """执行一次知识库入库：参数校验 → 注入隔离上下文 → 切片 → 写向量库。

    「数据打通」核心入口：把外部数据（文本 / Markdown）经统一用例灌入向量库（inmemory 或 Milvus）。
    """

    def __init__(self, store: VectorStorePort) -> None:
        self._store = store

    def execute(
        self, title: str, content: str, *, doc_id: str | None = None
    ) -> tuple[str, int]:
        # 隔离上下文缺失即拒绝（TC-12）
        ctx = require_tenant_context()

        if not content or not content.strip():
            raise BusinessError("AST-ERR-3001", message="文档内容不能为空")

        did = doc_id or f"ingested-{ctx.tenant_id}-{uuid.uuid4().hex[:12]}"
        doc = Document(id=did, tenant_id=ctx.tenant_id, title=title, content=content)
        # 单写者：切片数由 domain.chunking 决定（与向量库实现一致）
        count = len(split_document(doc))
        try:
            self._store.add(doc)
        except ExternalDependencyError:
            raise  # 4xxx 透传（向量库 / 嵌入不可用，AST-ERR-4002）
        except AsterismError:
            raise  # 已映射错误直接透传
        except Exception as exc:  # 意外：包装为内部错误（TC-15）
            raise SystemError("AST-ERR-5001", request_id=ctx.request_id, cause=exc) from exc
        return did, count
