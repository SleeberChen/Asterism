"""厂商全量 CRUD 端到端测试（真实 ASGI 应用 + per-request 业务库会话）。

覆盖 ``/api/v1/models/vendors`` 八端点经真实链路（鉴权头解析 → 隔离上下文注入 → 用例 →
业务库 → 统一错误响应）的完整行为，含：
- 缺 X-Tenant-Id 头 → 401（TC-12 边缘强制）；
- 登记 / 列 / 查 / 启停乐观锁(409) / 删模型 / 删厂商级联 / 删后查 404；
- 对外只暴露 AST-ERR 码（TC-16 不泄露堆栈）。

DB 用 sqlite 隔离（设 ``ASTERISM__DATABASE__URL`` 覆盖，走 ``db/migration/sqlite`` 迁移），
不依赖 MySQL；引擎单例按测试重置，表随临时库文件隔离。
"""

from __future__ import annotations

import os
import pathlib
import tempfile

import pytest

# 直接导入：若 TestClient 不可用，收集即失败（符合 TC-21「环境不可用判失败」）。
from fastapi.testclient import TestClient

from asterism.infrastructure.persistence.engine import reset_business_engine
from asterism.main import create_app

H = {"X-Tenant-Id": "t1", "X-User-Id": "admin"}


@pytest.fixture
def client():
    """按独立部署入口构建应用，sqlite 临时库隔离；引擎单例按测试重置。"""
    tmp = pathlib.Path(tempfile.mkdtemp())
    db_path = tmp / "business.db"
    os.environ["ASTERISM__DATABASE__URL"] = f"sqlite+aiosqlite:///{db_path.as_posix()}"
    reset_business_engine()
    app = create_app()
    with TestClient(app) as c:
        yield c
    reset_business_engine()
    os.environ.pop("ASTERISM__DATABASE__URL", None)


def test_missing_tenant_header_returns_401(client):
    resp = client.post(
        "/api/v1/models/vendors",
        json={"vendor_id": "v1", "plugin_registration_ref": "p1", "name": "O",
              "access_protocol": "openai", "base_url": "https://api",
              "credential_handle": "h", "default_timeout_budget_ms": 1000},
    )
    assert resp.status_code == 401


def test_vendor_full_crud_lifecycle(client):
    # 登记厂商
    resp = client.post(
        "/api/v1/models/vendors", headers=H,
        json={"vendor_id": "v1", "plugin_registration_ref": "p1", "name": "O",
              "access_protocol": "openai", "base_url": "https://api",
              "credential_handle": "h", "default_timeout_budget_ms": 1000},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    data = body["data"]  # 统一信封：业务负载在 data 内
    assert data["vendor_id"] == "v1"
    assert data["status"] == "停用"

    # 列厂商含它
    resp = client.get("/api/v1/models/vendors", headers=H)
    assert resp.status_code == 200
    assert len(resp.json()["data"]) == 1

    # 查厂商
    resp = client.get("/api/v1/models/vendors/v1", headers=H)
    assert resp.status_code == 200

    # 登记模型
    resp = client.post(
        "/api/v1/models/vendors/v1/models", headers=H,
        json={"model_id": "m1", "name": "gpt", "context_window": 128000,
              "modalities": ["text"], "is_default": True},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["data"]["model_id"] == "m1"

    # 列模型
    resp = client.get("/api/v1/models/vendors/v1/models", headers=H)
    assert resp.status_code == 200
    assert len(resp.json()["data"]) == 1

    # 启停：用当前 version
    ver = client.get("/api/v1/models/vendors/v1", headers=H).json()["data"]["version"]
    resp = client.put(
        "/api/v1/models/vendors/v1/status", headers=H,
        json={"status": "启用", "expected_version": ver},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == "启用"

    # 用过时版本号启停 → 409
    resp = client.put(
        "/api/v1/models/vendors/v1/status", headers=H,
        json={"status": "停用", "expected_version": ver},
    )
    assert resp.status_code == 409
    assert resp.json()["code"] == "AST-ERR-3005"

    # 删模型
    resp = client.delete("/api/v1/models/vendors/v1/models/m1", headers=H)
    assert resp.status_code == 204
    resp = client.get("/api/v1/models/vendors/v1/models", headers=H)
    assert resp.status_code == 200
    assert resp.json()["data"] == []

    # 删厂商（级联）
    resp = client.delete("/api/v1/models/vendors/v1", headers=H)
    assert resp.status_code == 204
    resp = client.get("/api/v1/models/vendors/v1", headers=H)
    assert resp.status_code == 404
    assert resp.json()["code"] == "AST-ERR-3003"


def test_get_missing_vendor_returns_404(client):
    resp = client.get("/api/v1/models/vendors/nope", headers=H)
    assert resp.status_code == 404
    assert resp.json()["code"] == "AST-ERR-3003"


def test_register_duplicate_plugin_ref_returns_400(client):
    payload = {"vendor_id": "v1", "plugin_registration_ref": "p1", "name": "O",
               "access_protocol": "openai", "base_url": "https://api",
               "credential_handle": "h", "default_timeout_budget_ms": 1000}
    assert client.post("/api/v1/models/vendors", headers=H, json=payload).status_code == 201
    resp = client.post(
        "/api/v1/models/vendors", headers=H,
        json={**payload, "vendor_id": "v2", "plugin_registration_ref": "p1", "name": "O2"},
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == "AST-ERR-3001"


# ---------------------------------------------------------------------------
# #3 供应商 API 管理：凭据轮换 / 连接配置更新
# ---------------------------------------------------------------------------
def test_rotate_vendor_credentials_bumps_version(client):
    reg = client.post(
        "/api/v1/models/vendors", headers=H,
        json={"vendor_id": "v1", "plugin_registration_ref": "p1", "name": "O",
              "access_protocol": "openai", "base_url": "https://api",
              "credential_handle": "h", "default_timeout_budget_ms": 1000},
    )
    assert reg.status_code == 201
    ver = reg.json()["data"]["version"]
    resp = client.post(
        "/api/v1/models/vendors/v1/credentials", headers=H,
        json={"new_credential_handle": "h-rotated", "expected_version": ver},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["version"] == ver + 1
    # 连接配置未被凭据轮换改动
    assert resp.json()["data"]["base_url"] == "https://api"


def test_rotate_vendor_credentials_stale_version_409(client):
    reg = client.post(
        "/api/v1/models/vendors", headers=H,
        json={"vendor_id": "v1", "plugin_registration_ref": "p1", "name": "O",
              "access_protocol": "openai", "base_url": "https://api",
              "credential_handle": "h", "default_timeout_budget_ms": 1000},
    )
    ver = reg.json()["data"]["version"]
    client.post(
        "/api/v1/models/vendors/v1/credentials", headers=H,
        json={"new_credential_handle": "h-rotated", "expected_version": ver},
    )
    resp = client.post(
        "/api/v1/models/vendors/v1/credentials", headers=H,
        json={"new_credential_handle": "h-again", "expected_version": ver},
    )
    assert resp.status_code == 409
    assert resp.json()["code"] == "AST-ERR-3005"


def test_update_vendor_connection_updates_config(client):
    reg = client.post(
        "/api/v1/models/vendors", headers=H,
        json={"vendor_id": "v1", "plugin_registration_ref": "p1", "name": "O",
              "access_protocol": "openai", "base_url": "https://api",
              "credential_handle": "h", "default_timeout_budget_ms": 1000},
    )
    ver = reg.json()["data"]["version"]
    resp = client.post(
        "/api/v1/models/vendors/v1/connection", headers=H,
        json={"access_protocol": "anthropic", "base_url": "https://new",
              "default_timeout_budget_ms": 2000, "expected_version": ver},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["base_url"] == "https://new"
    assert data["access_protocol"] == "anthropic"
    assert data["default_timeout_budget_ms"] == 2000
    assert data["version"] == ver + 1


def test_update_vendor_connection_missing_vendor_404(client):
    resp = client.post(
        "/api/v1/models/vendors/nope/connection", headers=H,
        json={"access_protocol": "openai", "base_url": "https://api",
              "default_timeout_budget_ms": 1000, "expected_version": 1},
    )
    assert resp.status_code == 404
    assert resp.json()["code"] == "AST-ERR-3003"


# ---------------------------------------------------------------------------
# #4 顶层跨厂商模型查询
# ---------------------------------------------------------------------------
def test_list_all_models_cross_vendor(client):
    # 注意：asterism_models.model_id 为全局主键，跨厂商模型须用不同 model_id
    for vid, pref, mid in (("v1", "p1", "m1"), ("v2", "p2", "m2")):
        assert client.post(
            "/api/v1/models/vendors", headers=H,
            json={"vendor_id": vid, "plugin_registration_ref": pref, "name": vid,
                  "access_protocol": "openai", "base_url": "https://api",
                  "credential_handle": "h", "default_timeout_budget_ms": 1000},
        ).status_code == 201
        assert client.post(
            "/api/v1/models/vendors/{}/models".format(vid), headers=H,
            json={"model_id": mid, "name": "gpt", "context_window": 128000,
                  "modalities": ["text"], "is_default": True},
        ).status_code == 201

    resp = client.get("/api/v1/models", headers=H)
    assert resp.status_code == 200
    models = resp.json()["data"]
    assert len(models) == 2
    # 顶层列表每个模型携带归属厂商
    assert {m["vendor_id"] for m in models} == {"v1", "v2"}
    assert {m["model_id"] for m in models} == {"m1", "m2"}


def test_get_model_by_id_cross_vendor(client):
    client.post(
        "/api/v1/models/vendors", headers=H,
        json={"vendor_id": "v1", "plugin_registration_ref": "p1", "name": "O",
              "access_protocol": "openai", "base_url": "https://api",
              "credential_handle": "h", "default_timeout_budget_ms": 1000},
    )
    client.post(
        "/api/v1/models/vendors/v1/models", headers=H,
        json={"model_id": "m1", "name": "gpt", "context_window": 128000,
              "modalities": ["text"], "is_default": True},
    )
    resp = client.get("/api/v1/models/m1", headers=H)
    assert resp.status_code == 200
    assert resp.json()["data"]["vendor_id"] == "v1"
    assert resp.json()["data"]["model_id"] == "m1"


def test_get_missing_model_by_id_404(client):
    resp = client.get("/api/v1/models/nope", headers=H)
    assert resp.status_code == 404
    assert resp.json()["code"] == "AST-ERR-3003"
