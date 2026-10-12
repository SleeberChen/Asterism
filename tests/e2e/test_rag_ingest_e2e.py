"""RAG 入库端到端测试（FastAPI TestClient；inmemory 后端，守 TC-01 不接外部库 / 网络）。

覆盖「数据打通」闭环：经 HTTP 边缘注入租户 → ingest 接口入库 → query 接口召回。
"""

from __future__ import annotations

import pytest

# 直接导入：若 TestClient 不可用，收集即失败（符合 TC-21「环境不可用判失败」）。
from fastapi.testclient import TestClient

from asterism.main import create_app


@pytest.fixture
def client():
    app = create_app()
    with TestClient(app) as c:
        yield c


def test_ingest_requires_tenant_header(client):
    """缺失 X-Tenant-Id 头 → 401（隔离上下文在边缘强制注入，TC-12）。"""
    resp = client.post("/api/v1/rag/ingest", json={"title": "x", "content": "y"})
    assert resp.status_code == 401


def test_ingest_then_query_loop(client):
    """ingest 一篇英文文档（空格分词，玩具嵌入可命中）→ query 召回该文档（数据通路闭环）。"""
    content = (
        "Asterism rag ingest demo validates the data pipeline. "
        "The pipeline stores chunks and retrieves by tenant."
    )
    resp = client.post(
        "/api/v1/rag/ingest",
        json={"title": "Ingest E2E", "content": content, "doc_id": "ingest-e2e-1"},
        headers={"X-Tenant-Id": "demo-tenant"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == "0"
    assert body["data"]["doc_id"] == "ingest-e2e-1"
    assert body["data"]["chunk_count"] == 1
    assert body["data"]["tenant_id"] == "demo-tenant"

    q = client.post(
        "/api/v1/rag/query",
        json={"query": "Asterism rag ingest demo validates the data pipeline"},
        headers={"X-Tenant-Id": "demo-tenant"},
    )
    assert q.status_code == 200
    sources = q.json()["data"]["sources"]
    assert any(s["doc_id"] == "ingest-e2e-1" for s in sources)


def test_empty_content_maps_to_param_error(client):
    """空内容入库映射为参数校验错误 AST-ERR-3001，HTTP 400。"""
    resp = client.post(
        "/api/v1/rag/ingest",
        json={"title": "x", "content": "   "},
        headers={"X-Tenant-Id": "demo-tenant"},
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == "AST-ERR-3001"
