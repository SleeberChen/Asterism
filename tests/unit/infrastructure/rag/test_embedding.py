"""嵌入提供方单测（离线，不依赖 fastembed / pymilvus）。"""

from __future__ import annotations

import pytest

from asterism.infrastructure.rag.embedding import (
    FastEmbedEmbeddingProvider,
    HashEmbeddingProvider,
)


def test_fastembed_default_model_is_supported():
    """守卫：默认模型名必须在 fastembed 支持列表内（防止写错名导致生产嵌入不可用）。"""
    fastembed = pytest.importorskip("fastembed")
    supported = {m["model"] for m in fastembed.TextEmbedding.list_supported_models()}
    assert FastEmbedEmbeddingProvider.DEFAULT_MODEL in supported


def test_fastembed_provider_dim_without_download():
    """未加载模型时，dim 返回构造期默认值（不触发下载）。"""
    p = FastEmbedEmbeddingProvider()  # 不触发下载（延迟）
    assert p.dim == 512


def test_hash_embedding_dim():
    p = HashEmbeddingProvider(dim=384)
    assert p.dim == 384


def test_hash_embedding_deterministic():
    p = HashEmbeddingProvider(dim=384)
    a = p.embed(["hello world", "foo bar"])
    b = p.embed(["hello world", "foo bar"])
    assert a == b  # 确定性
    assert len(a) == 2 and len(a[0]) == 384


def test_hash_embedding_distinct_texts_differ():
    p = HashEmbeddingProvider(dim=384)
    a = p.embed(["alpha beta"])[0]
    b = p.embed(["gamma delta"])[0]
    assert a != b


def test_hash_embedding_normalized():
    p = HashEmbeddingProvider(dim=64)
    vec = p.embed(["x"])[0]
    import math

    assert abs(math.sqrt(sum(v * v for v in vec)) - 1.0) < 1e-6
