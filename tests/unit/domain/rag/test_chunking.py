"""文档切片单测（单写者：inmemory 与 milvus 共用同一逻辑）。"""

from __future__ import annotations

from asterism.domain.rag.chunking import split_document
from asterism.domain.rag.model import Document


def _doc(content: str) -> Document:
    return Document(id="d1", tenant_id="t1", title="T", content=content)


def test_split_on_blank_lines():
    chunks = split_document(_doc("段落一。\n\n段落二。"))
    assert len(chunks) == 2
    assert all(c.tenant_id == "t1" for c in chunks)
    assert {c.id for c in chunks} == {"d1#0", "d1#1"}


def test_split_long_segment():
    chunks = split_document(_doc("A" * 5000), max_chars=1000)
    assert len(chunks) == 5
    assert all(c.embedding is None for c in chunks)


def test_split_empty_content():
    assert split_document(_doc("   \n\n  ")) == []
