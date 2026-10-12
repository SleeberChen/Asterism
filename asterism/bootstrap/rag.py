"""APP-RAG 装配（示范业务应用：内部知识库问答）。"""

from __future__ import annotations

from fastapi import FastAPI

from asterism.application.rag.use_case import RagIngestUseCase, RagQueryUseCase
from asterism.domain.rag.model import Document
from asterism.domain.rag.orchestrator import RagOrchestrator
from asterism.domain.rag.ports import VectorStorePort
from asterism.infrastructure.config.settings import load_settings
from asterism.infrastructure.rag.embedding import FastEmbedEmbeddingProvider
from asterism.infrastructure.rag.milvus_store import MilvusVectorStore
from asterism.infrastructure.rag.model_provider import StubGenerationProvider
from asterism.infrastructure.rag.vector_store import InMemoryVectorStore
from asterism.interfaces.rag.router import router as rag_router

# 演示租户（生产由 APP-SYSTEM / 星云提供）
DEMO_TENANT = "demo-tenant"


def _build_vector_store(settings) -> VectorStorePort:
    """按配置选择向量库后端（默认 inmemory 保演示；milvus 经配置启用，运行时暴露 AST-ERR-4002）。"""
    backend = str(settings.get("rag.vector.backend") or "inmemory").lower()
    if backend == "milvus":
        milvus = settings.get("rag.vector.milvus") or {}
        host = str(milvus.get("host", "172.17.0.4"))
        port = int(milvus.get("port", 19530))
        collection = str(milvus.get("collection", "asterism_rag"))
        embedding_cfg = settings.get("rag.vector.embedding") or {}
        model_name = str(embedding_cfg.get("model_name", FastEmbedEmbeddingProvider.DEFAULT_MODEL))
        embedder = FastEmbedEmbeddingProvider(model_name=model_name)
        return MilvusVectorStore(embedder, host=host, port=port, collection=collection)
    # 默认：进程内演示后端（零依赖）
    return InMemoryVectorStore()


def _seed_demo_knowledge(store: InMemoryVectorStore) -> None:
    """写入示范知识库（租户隔离维度显式标注）。"""
    store.add(
        Document(
            id="doc-asterism",
            tenant_id=DEMO_TENANT,
            title="Asterism 框架简介",
            content=(
                "Asterism 是企业级 AI 应用开发框架，基于 Python 3.13 与 FastAPI。\n\n"
                "它采用 DDD 四层架构：接口层、应用层、领域层、基础设施层，依赖单向。\n\n"
                "它遵循一切皆插件原则，模型、工具、技能、记忆四类能力统一经插件内核注册。\n\n"
                "它内置八通道租户隔离，缓存键强制包含 tenant_id，密钥不进入代码库。"
            ),
        )
    )


def wire_rag(app: FastAPI) -> None:
    """装配 RAG 应用：注册路由 + 装配用例（依赖倒置的合法装配点）。"""
    settings = load_settings()
    store = _build_vector_store(settings)
    # 仅进程内演示后端播种（Milvus 模式下由用户经 ingest 接口灌入，或 seed 走 ingest 路径）
    if isinstance(store, InMemoryVectorStore):
        _seed_demo_knowledge(store)
    generation = StubGenerationProvider()
    orchestrator = RagOrchestrator(retrieval=store, generation=generation)

    app.include_router(rag_router)
    app.state.rag_use_case = RagQueryUseCase(orchestrator=orchestrator)
    app.state.rag_ingest_use_case = RagIngestUseCase(store=store)
