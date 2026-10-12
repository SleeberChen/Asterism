"""RAG 端口（领域层定义，基础设施层实现；依赖倒置，TC-09 / §2.2）。"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from .model import Document, Query, RetrievalResult


@runtime_checkable
class RetrievalPort(Protocol):
    """检索端口：按查询返回相关片段（实现须按 tenant_id 隔离）。"""

    def retrieve(self, query: Query) -> list[RetrievalResult]:
        ...


@runtime_checkable
class GenerationPort(Protocol):
    """生成端口：依据上下文生成回答（实现须经插件内核注册，TC-11）。"""

    def generate(self, query: Query, context: str) -> str:
        ...


@runtime_checkable
class EmbeddingPort(Protocol):
    """嵌入端口：将文本编码为固定维稠密向量（基础设施层实现；Milvus 后端使用）。

    领域层只定义契约；具体实现（FastEmbed / 离线哈希）在基础设施层，业务不感知。
    """

    dim: int

    def embed(self, texts: list[str]) -> list[list[float]]:
        ...


@runtime_checkable
class VectorStorePort(Protocol):
    """向量库端口（读取 + 写入超集）。

    入库经应用层切片（见 ``asterism.domain.rag.chunking``，单写者），store 只收 ``Document``。
    ``InMemoryVectorStore`` 与 ``MilvusVectorStore`` 双实现；默认 inmemory 演示，milvus 经配置启用。
    """

    def add(self, doc: Document) -> None:
        ...

    def retrieve(self, query: Query) -> list[RetrievalResult]:
        ...
