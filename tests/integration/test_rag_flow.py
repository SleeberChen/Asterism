"""RAG 跨层集成测试（检索 + 生成 + 用例装配；租户隔离；错误映射）。

覆盖 P5 §6 集成层契约 IC：跨层装配通过端口（RetrievalPort / GenerationPort）解耦，
依赖倒置在组合根之外不越界；租户隔离贯穿检索与用例；错误映射符合统一错误码。

不接入真实向量库 / 模型（TC-01），使用进程内桩实现。
"""

from __future__ import annotations

import pytest

from asterism.application.rag.use_case import RagQueryUseCase
from asterism.domain.rag.model import Document
from asterism.domain.rag.orchestrator import RagOrchestrator
from asterism.infrastructure.rag.model_provider import StubGenerationProvider
from asterism.infrastructure.rag.vector_store import InMemoryVectorStore
from asterism.seedwork.context import (
    TenantContext,
    reset_tenant_context,
    set_tenant_context,
)
from asterism.seedwork.exceptions import BusinessError

DEMO_TENANT = "demo-tenant"


def _assemble(extra_docs=()):
    """装配示范 RAG 用例（不含真实密钥 / 网络，TC-01）。"""
    store = InMemoryVectorStore()
    store.add(
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
    for doc in extra_docs:
        store.add(doc)
    orch = RagOrchestrator(retrieval=store, generation=StubGenerationProvider())
    return RagQueryUseCase(orchestrator=orch)


def _with_context(tenant_id: str):
    ctx = TenantContext(tenant_id=tenant_id, user_id="u1", request_id="r1")
    return set_tenant_context(ctx)


def test_cross_layer_assembly_returns_answer():
    """检索 + 生成 + 用例跨层装配后，返回非空回答且回填租户。"""
    uc = _assemble()
    token = _with_context(DEMO_TENANT)
    try:
        ans = uc.execute("Asterism 的架构", request_id="r1")
    finally:
        reset_tenant_context(token)

    assert "根据已检索资料" in ans.text
    assert ans.tenant_id == DEMO_TENANT
    assert ans.sources  # 至少召回一条来源


def test_tenant_isolation_no_cross_leak():
    """跨租户数据不串：A 只见到 A 的文档，B 只见到 B 的文档。"""
    tb_doc = Document(
        id="db",
        tenant_id="tenant-b",
        title="B 私有",
        content="保密内容：仅 tenant-b 可见。\n\n这是租户 B 的私有知识。",
    )
    uc = _assemble(extra_docs=[tb_doc])

    t1 = _with_context(DEMO_TENANT)
    try:
        a1 = uc.execute("Asterism 插件", request_id="r1")
    finally:
        reset_tenant_context(t1)
    assert all(s.doc_id == "d1" for s in a1.sources)

    t2 = _with_context("tenant-b")
    try:
        a2 = uc.execute("私有知识", request_id="r2")
    finally:
        reset_tenant_context(t2)
    assert all(s.doc_id == "db" for s in a2.sources)


def test_empty_query_maps_to_param_error():
    """空查询映射为参数校验错误 AST-ERR-3001（HTTP 400，不兜底，TC-15/16）。"""
    uc = _assemble()
    token = _with_context(DEMO_TENANT)
    try:
        with pytest.raises(BusinessError) as ei:
            uc.execute("   ", request_id="r1")
    finally:
        reset_tenant_context(token)

    assert ei.value.code == "AST-ERR-3001"
    assert ei.value.http_status == 400
    # 对外文案不含堆栈 / 内网地址（TC-16）
    assert "Traceback" not in ei.value.message


def test_missing_context_maps_to_error():
    """隔离上下文缺失即拒绝（AST-ERR-2004，不兜底，TC-12）。"""
    uc = _assemble()
    # 不注入隔离上下文
    with pytest.raises(BusinessError) as ei:
        uc.execute("anything", request_id="r1")

    assert ei.value.code == "AST-ERR-2004"
    assert ei.value.http_status == 400
