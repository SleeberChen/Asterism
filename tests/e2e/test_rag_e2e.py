"""RAG 端到端测试（FastAPI TestClient 关键链路 K1）。

覆盖 P5 §6 端到端层：经真实 ASGI 应用工厂 ``create_app`` 走完整 HTTP 链路
（鉴权头解析 → 隔离上下文注入 → 用例 → 编排 → 端口实现 → 统一响应）。

环境约定（TC-21）：端到端测试不允许「环境不可用却判通过」。
- 依赖 ``starlette.testclient``（随 fastapi 安装）必须可用；缺失应直接失败而非跳过。
- 不依赖外部向量库 / 模型 / 网络（TC-01），使用进程内桩实现。
"""

from __future__ import annotations

import pytest

# 直接导入：若 TestClient 不可用，收集即失败（符合 TC-21「环境不可用判失败」）。
from fastapi.testclient import TestClient

from asterism.domain.rag.model import Document
from asterism.main import create_app


@pytest.fixture
def client():
    """按运行形态独立部署入口构建应用；TestClient 上下文触发 lifespan。"""
    app = create_app()
    with TestClient(app) as c:
        yield c


def test_healthz(client):
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_query_requires_tenant_header(client):
    """缺失 X-Tenant-Id 头 → 401（隔离上下文在边缘强制注入，TC-12）。"""
    resp = client.post("/api/v1/rag/query", json={"query": "Asterism 是什么"})
    assert resp.status_code == 401


def test_query_demo_tenant_returns_answer(client):
    """已播种租户可走通完整链路，返回带来源引用的回答。"""
    resp = client.post(
        "/api/v1/rag/query",
        json={"query": "Asterism 的架构", "top_k": 3},
        headers={"X-Tenant-Id": "demo-tenant"},
    )
    assert resp.status_code == 200
    body = resp.json()
    data = body["data"]  # 统一信封：业务负载在 data 内
    assert data["tenant_id"] == "demo-tenant"
    assert data["answer"]
    assert any(s["doc_id"] == "doc-asterism" for s in data["sources"])


def test_unknown_tenant_no_leak(client):
    """未播种租户不应看到 demo-tenant 知识（隔离在 HTTP 边缘生效）。"""
    resp = client.post(
        "/api/v1/rag/query",
        json={"query": "Asterism"},
        headers={"X-Tenant-Id": "stranger"},
    )
    assert resp.status_code == 200
    body = resp.json()
    data = body["data"]  # 统一信封：业务负载在 data 内
    assert data["tenant_id"] == "stranger"
    assert data["sources"] == []  # 未越权返回他租户内容


def test_empty_query_maps_to_param_error(client):
    """空查询（仅空白）映射为参数校验错误 AST-ERR-3001，HTTP 400。"""
    resp = client.post(
        "/api/v1/rag/query",
        json={"query": "   "},
        headers={"X-Tenant-Id": "demo-tenant"},
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == "AST-ERR-3001"


def test_tenant_isolation_via_second_tenant(client):
    """注入第二租户私有文档，验证第一租户检索不到它（八通道隔离，TC-12）。"""
    # 经组合根已装配的检索端口注入他租户文档（演示用，不引入新中间件）
    store = client.app.state.rag_use_case._orchestrator._retrieval
    store.add(
        Document(
            id="db",
            tenant_id="tenant-b",
            title="B 私有",
            content="保密：仅 tenant-b 可见。\n\n这是租户 B 的私有知识。",
        )
    )

    resp_b = client.post(
        "/api/v1/rag/query",
        json={"query": "私有知识"},
        headers={"X-Tenant-Id": "tenant-b"},
    )
    assert resp_b.status_code == 200
    assert all(s["doc_id"] == "db" for s in resp_b.json()["data"]["sources"])

    resp_a = client.post(
        "/api/v1/rag/query",
        json={"query": "私有知识"},
        headers={"X-Tenant-Id": "demo-tenant"},
    )
    assert resp_a.status_code == 200
    assert all(s["doc_id"] != "db" for s in resp_a.json()["data"]["sources"])
