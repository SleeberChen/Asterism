"""Milvus 向量库实现（VectorStorePort）。

- 单集合多租户；``tenant_id`` 标量过滤做八通道租户隔离（P4 第 8 章）。
- ``chunk_id`` 为主键，幂等 upsert（同名覆盖，重复入库不翻倍）。
- 连接 / 嵌入 / 检索失败统一映射为 ``AST-ERR-4002``（外部依赖异常），
  由上层决定回退（ADR-008 思路）。
- 不引入新中间件类型（P5 §4.1.2），仅作为可选向量库后端，经配置启用。
- ``pymilvus`` 延迟导入：inmemory 演示与单测路径无需安装即可导入本模块。
"""

from __future__ import annotations

from asterism.domain.rag.chunking import split_document
from asterism.domain.rag.model import Chunk, Document, Query, RetrievalResult
from asterism.domain.rag.ports import EmbeddingPort, VectorStorePort
from asterism.seedwork.exceptions import ExternalDependencyError

_DEFAULT_HOST = "172.17.0.4"
_DEFAULT_PORT = 19530
_DEFAULT_COLLECTION = "asterism_rag"


class MilvusVectorStore(VectorStorePort):
    """Milvus 向量库适配（pymilvus 简单客户端，延迟连接）。"""

    def __init__(
        self,
        embedder: EmbeddingPort,
        *,
        host: str = _DEFAULT_HOST,
        port: int = _DEFAULT_PORT,
        collection: str = _DEFAULT_COLLECTION,
        uri: str | None = None,
    ) -> None:
        self._embedder = embedder
        self._uri = uri or f"http://{host}:{port}"
        self._collection = collection
        self._client = None  # 延迟连接

    # ---- 延迟连接 ----
    def _connect(self):
        if self._client is None:
            try:
                from pymilvus import MilvusClient
            except ImportError as exc:  # pymilvus 未安装
                raise ExternalDependencyError(
                    "AST-ERR-4002", message="向量库客户端 pymilvus 未安装", cause=exc
                ) from exc
            try:
                self._client = MilvusClient(uri=self._uri)
            except Exception as exc:  # 连接失败（服务不可达 / 鉴权）
                raise ExternalDependencyError(
                    "AST-ERR-4002", message="无法连接 Milvus 向量库", cause=exc
                ) from exc
        return self._client

    def _ensure_collection(self, client, dim: int) -> None:
        try:
            from pymilvus import (
                CollectionSchema,
                DataType,
                FieldSchema,
            )

            if self._collection in client.list_collections():
                return
            fields = [
                FieldSchema(
                    name="chunk_id", dtype=DataType.VARCHAR, is_primary=True, max_length=64
                ),
                FieldSchema(name="tenant_id", dtype=DataType.VARCHAR, max_length=64),
                FieldSchema(name="doc_id", dtype=DataType.VARCHAR, max_length=64),
                FieldSchema(name="text", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="vector", dtype=DataType.FLOAT_VECTOR, dim=dim),
            ]
            schema = CollectionSchema(fields, enable_dynamic_field=False)
            index_params = client.prepare_index_params()
            index_params.add_index(
                field_name="vector", index_type="AUTOINDEX", metric_type="COSINE"
            )
            client.create_collection(
                collection_name=self._collection, schema=schema, index_params=index_params
            )
        except ExternalDependencyError:
            raise
        except Exception as exc:  # 建集合失败
            raise ExternalDependencyError(
                "AST-ERR-4002", message="创建 Milvus 集合失败", cause=exc
            ) from exc

    # ---- VectorStorePort ----
    def add(self, doc: Document) -> None:
        client = self._connect()
        self._ensure_collection(client, self._embedder.dim)
        chunks = split_document(doc)
        if not chunks:
            return
        texts = [c.text for c in chunks]
        try:
            vectors = self._embedder.embed(texts)
        except Exception as exc:  # 嵌入失败（模型不可用 / 下载失败）
            raise ExternalDependencyError(
                "AST-ERR-4002", message="文档嵌入失败（向量库依赖）", cause=exc
            ) from exc
        data = [
            {
                "chunk_id": c.id,
                "tenant_id": c.tenant_id,
                "doc_id": c.doc_id,
                "text": c.text,
                "vector": vec,
            }
            for c, vec in zip(chunks, vectors, strict=True)
        ]
        try:
            client.upsert(collection_name=self._collection, data=data)
            # 强制落盘：使刚写入的数据立即可被检索（ingest→query 即时一致）
            client.flush(self._collection)
        except Exception as exc:  # 写失败
            raise ExternalDependencyError(
                "AST-ERR-4002", message="写入 Milvus 失败", cause=exc
            ) from exc

    def retrieve(self, query: Query) -> list[RetrievalResult]:
        client = self._connect()
        self._ensure_collection(client, self._embedder.dim)
        try:
            # 检索前确保集合已加载（Milvus 未加载集合检索为空，TC：数据通路必须可见）
            client.load_collection(self._collection)
            qvec = self._embedder.embed([query.text])[0]
            hits = client.search(
                collection_name=self._collection,
                data=[qvec],
                limit=query.top_k,
                filter=f'tenant_id == "{query.tenant_id}"',
                output_fields=["chunk_id", "doc_id", "tenant_id", "text"],
            )
        except Exception as exc:  # 检索失败
            raise ExternalDependencyError(
                "AST-ERR-4002", message="检索 Milvus 失败", cause=exc
            ) from exc

        results: list[RetrievalResult] = []
        for hit in (hits[0] if hits else []):
            # pymilvus 3.x 返回实体字典；旧版返回带 .fields 的结果对象，两者皆兼容
            if isinstance(hit, dict):
                entity = hit
                distance = float(hit.get("distance", 0.0))
            else:
                entity = getattr(hit, "fields", None)
                if not isinstance(entity, dict):
                    entity = {
                        f: getattr(hit, f, None)
                        for f in ("chunk_id", "doc_id", "tenant_id", "text")
                    }
                distance = float(getattr(hit, "distance", 0.0))
            chunk = Chunk(
                id=entity.get("chunk_id"),
                doc_id=entity.get("doc_id"),
                tenant_id=entity.get("tenant_id"),
                text=entity.get("text") or "",
                embedding=None,
            )
            results.append(RetrievalResult(chunk=chunk, score=distance))
        return results
