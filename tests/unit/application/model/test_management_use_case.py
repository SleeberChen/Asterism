"""BC-MODEL 厂商管理用例单测（内存仓储，无 DB / 网络；全链路异步）。

覆盖：登记厂商/模型、列/查、启停乐观锁(409)、删厂商级联删模型、删缺失资源(404)、重复插件引用(400)。
隔离上下文由 fixture 注入（TC-12）；错误映射校验 AST-ERR 码与 HTTP 状态（TC-16）。
"""

from __future__ import annotations

import pytest

from asterism.application.model.management_use_case import ModelManagementUseCase
from asterism.domain.model.catalog import ModelCapability, ModelSpec, VendorConfig
from asterism.domain.model.repository import VendorRepository
from asterism.seedwork.context import TenantContext, reset_tenant_context, set_tenant_context
from asterism.seedwork.exceptions import BusinessError


@pytest.fixture
def ctx():
    token = set_tenant_context(TenantContext(tenant_id="t1", request_id="r1"))
    yield
    reset_tenant_context(token)


@pytest.fixture
def repo() -> VendorRepository:
    return VendorRepository()


async def test_register_and_get_vendor(ctx, repo):
    uc = ModelManagementUseCase(repo)
    v = await uc.register_vendor(
        vendor_id="v1", plugin_registration_ref="p1", name="O",
        config=VendorConfig("openai", "https://api", "h", 1000),
    )
    assert v.vendor_id == "v1"
    assert v.status == "停用"  # 登记即停用，待启停端点切换
    got = await uc.get_vendor(vendor_id="v1")
    assert got.name == "O"


async def test_register_model_and_list(ctx, repo):
    uc = ModelManagementUseCase(repo)
    await uc.register_vendor(
        vendor_id="v1", plugin_registration_ref="p1", name="O",
        config=VendorConfig("openai", "https://api", "h", 1000),
    )
    m = await uc.register_model(
        vendor_id="v1",
        spec=ModelSpec("m1", "gpt", ModelCapability(128000, ("text",)), is_default=True),
    )
    assert m.model_id == "m1"
    models = await uc.list_models(vendor_id="v1")
    assert len(models) == 1
    assert models[0].is_default is True


async def test_list_vendors_includes_registered(ctx, repo):
    uc = ModelManagementUseCase(repo)
    await uc.register_vendor(
        vendor_id="v1", plugin_registration_ref="p1", name="O",
        config=VendorConfig("openai", "https://api", "h", 1000),
    )
    await uc.register_vendor(
        vendor_id="v2", plugin_registration_ref="p2", name="A",
        config=VendorConfig("anthropic", "https://a", "h2", 1000),
    )
    vendors = await uc.list_vendors()
    assert {v.vendor_id for v in vendors} == {"v1", "v2"}


async def test_duplicate_plugin_ref_rejected_3001(ctx, repo):
    uc = ModelManagementUseCase(repo)
    await uc.register_vendor(
        vendor_id="v1", plugin_registration_ref="p1", name="O",
        config=VendorConfig("openai", "https://api", "h", 1000),
    )
    with pytest.raises(BusinessError) as exc:
        await uc.register_vendor(
            vendor_id="v2", plugin_registration_ref="p1", name="O2",
            config=VendorConfig("openai", "https://api", "h2", 1000),
        )
    assert exc.value.code == "AST-ERR-3001"
    assert exc.value.http_status == 400


async def test_get_missing_vendor_404(ctx, repo):
    uc = ModelManagementUseCase(repo)
    with pytest.raises(BusinessError) as exc:
        await uc.get_vendor(vendor_id="nope")
    assert exc.value.code == "AST-ERR-3003"
    assert exc.value.http_status == 404


async def test_enable_disable_with_optimistic_lock(ctx, repo):
    uc = ModelManagementUseCase(repo)
    v = await uc.register_vendor(
        vendor_id="v1", plugin_registration_ref="p1", name="O",
        config=VendorConfig("openai", "https://api", "h", 1000),
    )
    enabled = await uc.set_vendor_status(vendor_id="v1", status="启用", expected_version=v.version)
    assert enabled.status == "启用"
    # 用过时版本号提交应触发乐观锁冲突（409）
    with pytest.raises(BusinessError) as exc:
        await uc.set_vendor_status(vendor_id="v1", status="停用", expected_version=v.version)
    assert exc.value.code == "AST-ERR-3005"
    assert exc.value.http_status == 409


async def test_delete_vendor_cascades_models(ctx, repo):
    uc = ModelManagementUseCase(repo)
    await uc.register_vendor(
        vendor_id="v1", plugin_registration_ref="p1", name="O",
        config=VendorConfig("openai", "https://api", "h", 1000),
    )
    await uc.register_model(vendor_id="v1", spec=ModelSpec("m1", "gpt", ModelCapability(1000)))
    await uc.delete_vendor(vendor_id="v1")
    with pytest.raises(BusinessError) as exc:
        await uc.get_vendor(vendor_id="v1")
    assert exc.value.code == "AST-ERR-3003"
    # 模型随聚合根级联删除，再删应 404
    with pytest.raises(BusinessError) as exc2:
        await uc.delete_model(vendor_id="v1", model_id="m1")
    assert exc2.value.code == "AST-ERR-3003"


async def test_delete_missing_model_404(ctx, repo):
    uc = ModelManagementUseCase(repo)
    await uc.register_vendor(
        vendor_id="v1", plugin_registration_ref="p1", name="O",
        config=VendorConfig("openai", "https://api", "h", 1000),
    )
    with pytest.raises(BusinessError) as exc:
        await uc.delete_model(vendor_id="v1", model_id="missing")
    assert exc.value.code == "AST-ERR-3003"


# --- #3 供应商 API 管理：凭据轮换 / 连接配置更新 ---
async def test_rotate_vendor_credentials(ctx, repo):
    uc = ModelManagementUseCase(repo)
    v = await uc.register_vendor(
        vendor_id="v1", plugin_registration_ref="p1", name="O",
        config=VendorConfig("openai", "https://api", "h", 1000),
    )
    rotated = await uc.rotate_vendor_credentials(
        vendor_id="v1", new_credential_handle="h2", expected_version=v.version
    )
    assert rotated.config.credential_handle == "h2"
    assert rotated.config.base_url == "https://api"  # 连接配置保留


async def test_update_vendor_connection(ctx, repo):
    uc = ModelManagementUseCase(repo)
    v = await uc.register_vendor(
        vendor_id="v1", plugin_registration_ref="p1", name="O",
        config=VendorConfig("openai", "https://api", "h", 1000),
    )
    upd = await uc.update_vendor_connection(
        vendor_id="v1", access_protocol="anthropic", base_url="https://a",
        default_timeout_budget_ms=2000, expected_version=v.version,
    )
    assert upd.config.base_url == "https://a"
    assert upd.config.credential_handle == "h"  # 凭据保留


# --- #4 顶层跨厂商模型查询 ---
async def test_list_all_models_cross_vendor(ctx, repo):
    uc = ModelManagementUseCase(repo)
    await uc.register_vendor(vendor_id="v1", plugin_registration_ref="p1", name="O",
                             config=VendorConfig("openai", "https://api", "h", 1000))
    await uc.register_model(vendor_id="v1", spec=ModelSpec("m1", "gpt", ModelCapability(128000)))
    await uc.register_vendor(vendor_id="v2", plugin_registration_ref="p2", name="A",
                             config=VendorConfig("anthropic", "https://a", "h2", 1000))
    await uc.register_model(vendor_id="v2", spec=ModelSpec("m2", "claude", ModelCapability(200000)))
    rows = await uc.list_all_models()
    assert {(vid, m.model_id) for vid, m in rows} == {("v1", "m1"), ("v2", "m2")}


async def test_get_model_by_id_cross_vendor(ctx, repo):
    uc = ModelManagementUseCase(repo)
    await uc.register_vendor(vendor_id="v1", plugin_registration_ref="p1", name="O",
                             config=VendorConfig("openai", "https://api", "h", 1000))
    await uc.register_model(vendor_id="v1", spec=ModelSpec("m1", "gpt", ModelCapability(128000)))
    vid, m = await uc.get_model(model_id="m1")
    assert vid == "v1" and m.model_id == "m1"


async def test_get_missing_model_404(ctx, repo):
    uc = ModelManagementUseCase(repo)
    with pytest.raises(BusinessError) as exc:
        await uc.get_model(model_id="nope")
    assert exc.value.code == "AST-ERR-3003"
