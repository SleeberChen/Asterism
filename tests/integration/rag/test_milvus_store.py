"""Milvus 向量库集成测试（针对真实 Milvus 2.x；不可达则跳过）。

覆盖范围（P5 §6 集成层）：连接 / 建集合 / 标量过滤租户隔离 / 主键幂等 upsert / 检索。
- 仅依赖可选外部服务 Milvus；不可达 → pytest.skip（不伪造通过，TC-21 精神）。
- 嵌入优先用 FastEmbed（生产路径）；模型不可用（无网络下载）则降级 HashEmbeddingProvider（离线）。
- 使用按时间命名的独立集合，teardown 删除，互不干扰。
"""

from __future__ import annotations

import os
import time

import pytest

pytest.importorskip("pymilvus")

from asterism.domain.rag.model import Document, Query  # noqa: E402
from asterism.infrastructure.rag.embedding import (  # noqa: E402
    FastEmbedEmbeddingProvider,
    HashEmbeddingProvider,
)
from asterism.infrastructure.rag.milvus_store import MilvusVectorStore  # noqa: E402

HOST = os.getenv("ASTERISM__RAG__VECTOR__MILVUS__HOST", "172.17.0.4")
PORT = int(os.getenv("ASTERISM__RAG__VECTOR__MILVUS__PORT", "19530"))
COLLECTION = f"asterism_rag_it_{int(time.time())}"

# 离线集成环境（无 HuggingFace 网络、无法下载 FastEmbed 模型）可通过此开关强制哈希回退，
# 仅验证 Milvus 数据通路（连通 / 隔离 / 幂等），不阻断真实 Milvus 流水线验证。
FORCE_HASH = os.getenv("ASTERISM__RAG__INTEGRATION__FORCE_HASH", "").lower() in ("1", "true", "yes")


def _client():
    from pymilvus import MilvusClient

    return MilvusClient(uri=f"http://{HOST}:{PORT}")


@pytest.fixture
def store():
    # 连通性探针：不可达则跳过（外部服务可选）
    try:
        probe = _client()
        probe.list_collections()
    except Exception as exc:
        pytest.skip(f"Milvus 不可达（{HOST}:{PORT}），跳过集成测试：{exc}")

    # 嵌入提供方：优先真实 FastEmbed，失败降级离线哈希
    if FORCE_HASH:
        embedder = HashEmbeddingProvider()
        kind = "hash(forced)"
    else:
        try:
            embedder = FastEmbedEmbeddingProvider()
            embedder.embed(["probe"])  # 触发模型加载 / 下载
            kind = "fastembed"
        except Exception as exc:  # 模型不可用（无网络 / 未安装）
            embedder = HashEmbeddingProvider()
            kind = f"hash(fallback:{type(exc).__name__})"
    print(f"[milvus-it] 嵌入提供方 = {kind}")

    # 清理旧集合，保证全新起点
    try:
        c = _client()
        if COLLECTION in c.list_collections():
            c.drop_collection(COLLECTION)
    except Exception:
        pass

    s = MilvusVectorStore(embedder, host=HOST, port=PORT, collection=COLLECTION)
    yield s

    # teardown：删除测试集合
    try:
        c = _client()
        if COLLECTION in c.list_collections():
            c.drop_collection(COLLECTION)
    except Exception:
        pass


def test_upsert_and_tenant_isolation(store):
    """跨租户数据不串：A 只见到 A，B 只见到 B（八通道隔离）。"""
    store.add(
        Document(
            id="d-a", tenant_id="tenant-a", title="A", content="Alpha 专有知识。\n\nAlpha 第二段。"
        )
    )
    store.add(
        Document(
            id="d-b", tenant_id="tenant-b", title="B", content="Beta 专有知识。\n\nBeta 第二段。"
        )
    )

    res_a = store.retrieve(Query(tenant_id="tenant-a", text="Alpha"))
    assert len(res_a) > 0, "tenant-a 应召回自身切片"
    assert all(r.chunk.tenant_id == "tenant-a" for r in res_a)

    res_b = store.retrieve(Query(tenant_id="tenant-b", text="Alpha"))
    assert all(r.chunk.tenant_id == "tenant-b" for r in res_b), "tenant-b 查询不得越权返回 tenant-a"
    assert all(r.chunk.doc_id != "d-a" for r in res_b)


def test_idempotent_upsert(store):
    """主键幂等：重复 add 同名文档，chunk 数不因翻倍（支撑覆盖写）。"""
    doc = Document(id="d1", tenant_id="t1", title="X", content="内容一。\n\n内容二。")
    store.add(doc)
    first_ids = {r.chunk.id for r in store.retrieve(Query(tenant_id="t1", text="内容"))}
    store.add(doc)  # 再次 upsert 同文档（同 chunk_id）
    second_ids = {r.chunk.id for r in store.retrieve(Query(tenant_id="t1", text="内容"))}
    assert first_ids == second_ids


def test_unknown_tenant_empty(store):
    """未播种租户检索为空，不越权。"""
    res = store.retrieve(Query(tenant_id="nobody", text="anything"))
    assert res == []
