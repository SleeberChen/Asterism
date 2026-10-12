"""RAG 基础设施层（示范应用）：检索与生成的具体实现。

实现领域端口（RetrievalPort / GenerationPort / VectorStorePort / EmbeddingPort）；只依赖领域层与插件内核，
不反向调用应用层 / 接口层（TC-09）。真实向量库 / 嵌入经适配层接入：
- ``vector_store.InMemoryVectorStore``：进程内演示后端（零依赖，默认）。
- ``milvus_store.MilvusVectorStore``：Milvus 后端（真实嵌入 + 持久化 + 租户隔离），经配置启用。
- ``embedding.FastEmbedEmbeddingProvider`` / ``HashEmbeddingProvider``：嵌入提供方。
- ``model_provider.StubGenerationProvider``：生成适配（演示）。
"""
