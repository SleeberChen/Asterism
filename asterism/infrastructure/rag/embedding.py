"""嵌入提供方（实现 EmbeddingPort）。

- ``FastEmbedEmbeddingProvider``：真实本地嵌入（默认 BAAI/bge-small-zh-v1.5，
  离线、中文可用），生产 Milvus 后端使用。
- ``HashEmbeddingProvider``：零依赖确定性固定维嵌入，供离线 / 集成测试（免模型下载）。

为不污染零依赖演示与单测，``fastembed`` 采用**延迟导入**（模块导入不触发安装/下载依赖）。
"""

from __future__ import annotations

import hashlib
import math

from asterism.domain.rag.ports import EmbeddingPort


class HashEmbeddingProvider(EmbeddingPort):
    """确定性哈希嵌入：将词频映射到固定维稠密向量，零依赖、可离线。

    不具语义，仅用于离线验证向量库数据通路（连通性 / 隔离 / 幂等）；生产请用 FastEmbed。
    """

    def __init__(self, dim: int = 384) -> None:
        self._dim = dim

    @property
    def dim(self) -> int:
        return self._dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [_hash_vector(t, self._dim) for t in texts]


def _hash_vector(text: str, dim: int) -> list[float]:
    vec = [0.0] * dim
    for tok in text.lower().split():
        h = int.from_bytes(hashlib.md5(tok.encode("utf-8")).digest()[:4], "big")
        vec[h % dim] += 1.0
    norm = math.sqrt(sum(v * v for v in vec))
    if norm > 0.0:
        vec = [v / norm for v in vec]
    return vec


class FastEmbedEmbeddingProvider(EmbeddingPort):
    """真实本地嵌入（FastEmbed，默认 BAAI/bge-small-zh-v1.5，中文专用、离线可用）。

    构造期即暴露 ``dim``（默认模型真实维度 512，不触发加载）；首次调用 ``embed`` 才
    加载并下载模型权重（约数十 MB），需网络；生产 Milvus 后端默认使用。``fastembed``
    延迟导入：模块导入不要求已安装。
    """

    # 默认模型：中文语义检索优化、体积小（dim=512）
    DEFAULT_MODEL = "BAAI/bge-small-zh-v1.5"

    def __init__(self, model_name: str = DEFAULT_MODEL, dim: int = 512) -> None:
        self._model_name = model_name
        self._dim = dim  # 构造期默认值；加载模型后以真实维度覆盖（避免建集合维度不匹配）
        self._model = None  # 延迟加载

    @property
    def dim(self) -> int:
        # 构造期默认值（default 模型 BAAI/bge-small-zh-v1.5 的真实维度 = 512）。
        # 真实维度仅在 _ensure_model() 内、首次 embed 时按模型实际 embedding_size 覆盖，
        # 不在此处触发加载/下载，保证离线（无 HuggingFace 网络）也能安全读取维度。
        return self._dim

    def _ensure_model(self):
        if self._model is None:
            try:
                from fastembed import TextEmbedding  # 延迟导入，避免硬依赖
            except ImportError as exc:  # fastembed 未安装
                from asterism.seedwork.exceptions import ExternalDependencyError

                raise ExternalDependencyError(
                    "AST-ERR-4002", message="嵌入模型依赖 fastembed 未安装", cause=exc
                ) from exc
            self._model = TextEmbedding(model_name=self._model_name)
            try:  # 以模型真实维度为准，覆盖构造期默认值
                self._dim = int(self._model.embedding_size)
            except Exception:
                pass
        return self._model

    def embed(self, texts: list[str]) -> list[list[float]]:
        model = self._ensure_model()
        out: list[list[float]] = []
        for vec in model.embed(texts):
            out.append([float(x) for x in vec])
        return out
