"""RAG 编排领域服务（纯逻辑，可单测，无 IO、无框架依赖）。

流程：检索 → 组装上下文（受 max_context_tokens 约束）→ 生成。
租户隔离由传入的 ``Query.tenant_id`` 保证（该值来自框架注入的隔离上下文，TC-12）。
"""

from __future__ import annotations

from typing import List

from .model import Answer, Query, RetrievalResult, SourceRef
from .ports import GenerationPort, RetrievalPort


class RagOrchestrator:
    def __init__(self, retrieval: RetrievalPort, generation: GenerationPort) -> None:
        self._retrieval = retrieval
        self._generation = generation

    def answer(self, query: Query) -> Answer:
        if not query.text or not query.text.strip():
            raise ValueError("query text 为空")
        results = self._retrieval.retrieve(query)
        context = self._assemble_context(results, query.max_context_tokens)
        text = self._generation.generate(query, context)
        sources = [
            SourceRef(doc_id=r.chunk.doc_id, chunk_id=r.chunk.id, snippet=r.chunk.text[:160])
            for r in results
        ]
        return Answer(text=text, tenant_id=query.tenant_id, request_id=None, sources=sources)

    @staticmethod
    def _assemble_context(results: List[RetrievalResult], max_tokens: int) -> str:
        parts: List[str] = []
        used = 0
        for r in results:
            snippet = r.chunk.text
            est = max(1, len(snippet) // 2)  # 粗估 token 数
            if used + est > max_tokens:
                keep = max(0, (max_tokens - used) * 2)
                snippet = snippet[:keep]
            if not snippet:
                continue
            parts.append(f"- {snippet}")
            used += est
            if used >= max_tokens:
                break
        return "\n".join(parts)
