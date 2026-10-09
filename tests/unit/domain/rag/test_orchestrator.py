"""领域层 RAG 编排单元测试（无 IO、纯逻辑，外部依赖一律 mock）。"""

from __future__ import annotations

import pytest

from asterism.domain.rag.model import Chunk, Query, RetrievalResult
from asterism.domain.rag.orchestrator import RagOrchestrator


class _FakeRetrieval:
    def __init__(self, results):
        self.results = results

    def retrieve(self, query):
        return self.results


class _FakeGen:
    def generate(self, query, context):
        return f"ANSWER<<{context[:24]}>>"


def _chunk(tenant_id="t1", text="Asterism DDD"):
    return Chunk(id="c1", doc_id="d1", tenant_id=tenant_id, text=text)


def test_answer_assembles_context_and_sources():
    orch = RagOrchestrator(_FakeRetrieval([RetrievalResult(chunk=_chunk(), score=0.9)]), _FakeGen())
    ans = orch.answer(Query(tenant_id="t1", text="架构"))
    assert "ANSWER" in ans.text
    assert ans.sources[0].chunk_id == "c1"
    assert ans.tenant_id == "t1"


def test_empty_query_raises_value_error():
    orch = RagOrchestrator(_FakeRetrieval([]), _FakeGen())
    with pytest.raises(ValueError):
        orch.answer(Query(tenant_id="t1", text="   "))


def test_context_truncated_by_max_tokens():
    long_text = "词 " * 1000
    orch = RagOrchestrator(_FakeRetrieval([RetrievalResult(chunk=_chunk(text=long_text), score=1.0)]), _FakeGen())
    ans = orch.answer(Query(tenant_id="t1", text="x", max_context_tokens=50))
    # 上下文被 max_context_tokens 约束（粗估 <= 约 2*max_tokens 字符）
    assert len(ans.text) < 2000
