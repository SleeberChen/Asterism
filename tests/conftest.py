"""共享测试 fixtures。

- ``tenant_ctx``：注入隔离上下文（框架统一注入，TC-12），测试内模拟请求入口。
- ``store`` / ``use_case``：示范 RAG 的检索与用例装配（无真实密钥 / 网络，TC-01）。
- 测试数据不含生产真实数据（TC-19）。
"""

from __future__ import annotations

import pytest

from asterism.application.rag.use_case import RagQueryUseCase
from asterism.domain.rag.model import Document
from asterism.domain.rag.orchestrator import RagOrchestrator
from asterism.infrastructure.rag.model_provider import StubGenerationProvider
from asterism.infrastructure.rag.vector_store import InMemoryVectorStore
from asterism.seedwork.context import TenantContext, reset_tenant_context, set_tenant_context

DEMO_TENANT = "demo-tenant"


@pytest.fixture
def store() -> InMemoryVectorStore:
    s = InMemoryVectorStore()
    s.add(
        Document(
            id="d1",
            tenant_id=DEMO_TENANT,
            title="Asterism 简介",
            content=(
                "Asterism 采用 DDD 四层架构。\n\n"
                "它遵循一切皆插件原则，模型工具技能记忆统一注册。\n\n"
                "它内置八通道租户隔离，缓存键含 tenant_id。"
            ),
        )
    )
    return s


@pytest.fixture
def use_case(store: InMemoryVectorStore) -> RagQueryUseCase:
    gen = StubGenerationProvider()
    orch = RagOrchestrator(retrieval=store, generation=gen)
    return RagQueryUseCase(orchestrator=orch)


@pytest.fixture
def tenant_ctx():
    ctx = TenantContext(tenant_id=DEMO_TENANT, user_id="u1", request_id="r1")
    token = set_tenant_context(ctx)
    yield ctx
    reset_tenant_context(token)
