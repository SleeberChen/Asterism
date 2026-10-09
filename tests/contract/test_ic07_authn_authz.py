"""契约测试 `T-CONTRACT-07` → `IC-07` 认证授权契约。

测试意图（P3 02-应用间契约.md）：
- 未认证访问拒绝率 = 100%（样本 ≥ 10 入口）；
- 认证不可用**拒绝放行**（降级次数 = 0，即禁止降级为免认证）。

样本说明：本骨架当前仅装配 5 个受保护入口（rag / models / sys×3），
低于契约要求的 ≥10；此处对**现有全部入口**实证 100% 拒绝，不足样本数如实标注。
"""
from __future__ import annotations

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from asterism.interfaces.compliance.deps import require_permission, resolve_tenant_context
from asterism.main import create_app

PROTECTED_ENTRYPOINTS = [
    ("POST", "/api/v1/rag/query"),
    ("POST", "/api/v1/models/invoke"),
    ("GET", "/api/v1/sys/users"),
    ("GET", "/api/v1/sys/roles"),
    ("GET", "/api/v1/sys/menus"),
]


@pytest.fixture
def client():
    app = create_app()
    with TestClient(app) as c:
        yield c


def test_unauthenticated_access_is_rejected_on_every_entrypoint(client):
    """缺失 `X-Tenant-Id` 一律 401：拒绝率 100%（不兜底放行）。"""
    for method, path in PROTECTED_ENTRYPOINTS:
        resp = client.request(method, path, json={"query": "x", "prompt": "x"})
        assert resp.status_code == 401, f"{method} {path} 未拒绝未认证访问"


def test_authz_unavailable_denies_instead_of_downgrading():
    """鉴权用例未装配 → 403 拒绝服务，**不降级为免认证放行**（降级次数 = 0）。"""
    app = FastAPI()

    @app.get("/protected")
    async def _protected(_decision=Depends(require_permission("rag", "read"))):
        return {"ok": True}

    with TestClient(app) as c:
        resp = c.get("/protected", headers={"X-Tenant-Id": "demo-tenant"})
    assert resp.status_code == 403


def test_tenant_context_injection_is_the_single_entrypoint():
    """`resolve_tenant_context` 为隔离上下文统一注入点（TC-12），缺失租户即 401。"""
    app = FastAPI()

    @app.get("/ctx")
    async def _ctx(ctx=Depends(resolve_tenant_context)):
        return {"tenant_id": ctx.tenant_id}

    with TestClient(app) as c:
        assert c.get("/ctx").status_code == 401
        ok = c.get("/ctx", headers={"X-Tenant-Id": "t-1", "X-User-Id": "u-1"})
    assert ok.status_code == 200
    assert ok.json()["tenant_id"] == "t-1"
