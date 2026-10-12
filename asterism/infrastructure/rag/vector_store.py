"""进程内向量库（演示用，实现 VectorStorePort）。

- 租户命名空间隔离：检索仅返回同 ``tenant_id`` 的切片（八通道隔离，P4 第 8 章）。
- 确定性词频向量 + 余弦相似度（无外部嵌入模型 / 网络，零依赖保演示可跑）。
- 演示缓存键含 tenant_id（TC-13）：经统一构造器生成键，禁止手拼。

生产替换：实现同一 ``VectorStorePort`` 即可接入真实向量库（Milvus，P5 §4.1.2，不引入新中间件类型）。
"""

from __future__ import annotations

import hashlib
import math
from collections import defaultdict

from asterism.domain.rag.chunking import split_document
from asterism.domain.rag.model import Chunk, Document, Query, RetrievalResult
from asterism.infrastructure.cache import MemoryCache, build_cache_key
from asterism.seedwork.logging import get_logger

logger = get_logger(__name__)


def _embed(text: str) -> dict[str, float]:
    vec: dict[str, float] = defaultdict(float)
    for tok in text.lower().split():
        vec[tok] += 1.0
    return dict(vec)


def _cosine(a: dict[str, float], b: dict[str, float]) -> float:
    if not a or not b:
        return 0.0
    dot = sum(v * b.get(k, 0.0) for k, v in a.items())
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


class InMemoryVectorStore:
    """进程内向量库（演示）：实现 VectorStorePort（结构子类型）。

    嵌入为内置确定性词频向量，无真实语义、无持久化；仅供零依赖演示与单测（TC-01）。
    """

    def __init__(self) -> None:
        self._by_tenant: dict[str, list[Chunk]] = defaultdict(list)
        self._cache = MemoryCache()

    def add(self, doc: Document) -> None:
        for chunk in split_document(doc):
            # 嵌入留空：检索时按文本惰性重算（演示级；避免与 Chunk.embedding 类型耦合）
            self._by_tenant[doc.tenant_id].append(chunk)
        logger.info("文档已入库", extra={"doc_id": doc.id, "tenant_id": doc.tenant_id})

    def retrieve(self, query: Query) -> list[RetrievalResult]:
        # 缓存键强制含 tenant_id（TC-13）；进程内缓存，单点已登记（TC-18）
        qhash = hashlib.sha1(query.text.encode("utf-8")).hexdigest()[:12]
        cache_key = build_cache_key("rag", "retrieve", qhash, tenant_id=query.tenant_id)
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached  # type: ignore[return-value]

        qvec = _embed(query.text)
        candidates = self._by_tenant.get(query.tenant_id, [])
        scored = [
            RetrievalResult(chunk=c, score=_cosine(qvec, c.embedding or _embed(c.text)))
            for c in candidates
        ]
        scored.sort(key=lambda r: r.score, reverse=True)
        result = scored[: query.top_k]
        self._cache.set(cache_key, result)
        return result
