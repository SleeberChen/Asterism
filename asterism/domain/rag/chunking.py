"""RAG 文档切片（单写者：所有向量库实现共用，避免切片逻辑漂移，P3 §5 单写者表）。

切片策略：先按空行分段；超长段再按字符上限硬切。演示级策略，生产可换语义 / 滑动窗口（记开放项）。
切片键 ``id`` 形如 ``{doc_id}#{i}``，幂等（同名 chunk 可覆盖写，支撑 Milvus upsert）。
"""

from __future__ import annotations

from .model import Chunk, Document

_MAX_CHARS = 2000  # 单切片字符上限（超长段落再切）


def split_document(doc: Document, max_chars: int = _MAX_CHARS) -> list[Chunk]:
    """将 ``Document`` 切分为带租户维度的 ``Chunk`` 列表（嵌入字段留空，由具体向量库填充）。"""
    segments = [s.strip() for s in doc.content.split("\n\n") if s.strip()]
    chunks: list[Chunk] = []
    idx = 0
    for seg in segments:
        if len(seg) <= max_chars:
            chunks.append(_make_chunk(doc, idx, seg))
            idx += 1
            continue
        # 超长段：按 max_chars 硬切（演示级；生产可换语义 / 滑动窗口，记开放项）
        for start in range(0, len(seg), max_chars):
            piece = seg[start : start + max_chars].strip()
            if piece:
                chunks.append(_make_chunk(doc, idx, piece))
                idx += 1
    return chunks


def _make_chunk(doc: Document, idx: int, text: str) -> Chunk:
    return Chunk(
        id=f"{doc.id}#{idx}",
        doc_id=doc.id,
        tenant_id=doc.tenant_id,
        text=text,
        embedding=None,  # 由具体向量库实现填充
    )
