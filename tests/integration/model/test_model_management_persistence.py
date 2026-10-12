"""BC-MODEL 厂商管理集成测试（默认 MySQL 业务库异步 + 真实 SqlVendorRepository）。

验证：经业务库落盘的全量 CRUD 关键路径——
- 删厂商级联清 models 表（FK RESTRICT 下先清子表）；
- 删后查厂商 → 404（AST-ERR-3003）；
- 启停乐观锁冲突 → 409（AST-ERR-3005）；
- 租户行级隔离（跨租户不可见）。
默认目标 = 配置的业务库（异步 MySQL 方言）；可用 AST-ERR__DATABASE__URL 覆盖为 sqlite。
每次用例前清空 BC-MODEL 三表，保证可重复跑。每个用例显式 dispose 引擎，避免连接池泄漏。
"""

from __future__ import annotations

import os

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from asterism.application.model.management_use_case import ModelManagementUseCase
from asterism.domain.model.catalog import ModelCapability, ModelSpec, VendorConfig
from asterism.infrastructure.persistence.db import init_db, make_business_engine, make_engine
from asterism.infrastructure.persistence.model_repository import SqlVendorRepository
from asterism.seedwork.context import TenantContext, reset_tenant_context, set_tenant_context
from asterism.seedwork.exceptions import BusinessError


async def _make_engine():
    url = os.environ.get("ASTERISM__DATABASE__URL")
    engine = make_engine(url) if url else make_business_engine()
    await init_db(engine)
    await _reset_bc_model_tables(engine)
    return engine


def _require_test_db_for_reset(engine) -> None:
    """安全护栏：仅在显式测试库上清空 BC-MODEL 三表，杜绝误清外部/生产 MySQL。

    - 显式 opt-in：环境变量 ASTERISM__INTEGRATION_TEST_DB 非空；
    - 或数据库名（URL 路径末段）含 'test'（大小写不敏感）。
    否则跳过清空（该集成用例整体 skip），绝不 DELETE 真实库。
    """
    url = str(engine.url)
    db_name = url.rstrip("/").split("/")[-1].split("?")[0]
    opt_in = bool(os.environ.get("ASTERISM__INTEGRATION_TEST_DB"))
    if not (opt_in or "test" in db_name.lower()):
        pytest.skip(
            f"拒绝在疑似非测试库 '{db_name}' 上清空 BC-MODEL 表；"
            f"如需运行集成测试请设 ASTERISM__INTEGRATION_TEST_DB=1 或使用 *_test 数据库"
        )


async def _reset_bc_model_tables(engine):
    _require_test_db_for_reset(engine)
    dialect = engine.dialect.name
    async with engine.begin() as conn:
        if dialect == "mysql":
            await conn.execute(text("SET FOREIGN_KEY_CHECKS=0"))
            for t in ("asterism_models", "asterism_vendors", "asterism_prompt_templates"):
                await conn.execute(text(f"DELETE FROM {t}"))
            await conn.execute(text("SET FOREIGN_KEY_CHECKS=1"))
        else:
            await conn.execute(text("DELETE FROM asterism_models"))
            await conn.execute(text("DELETE FROM asterism_vendors"))
            await conn.execute(text("DELETE FROM asterism_prompt_templates"))


async def test_management_delete_vendor_cascades_models_sql():
    engine = await _make_engine()
    try:
        async with AsyncSession(engine, expire_on_commit=False) as s:
            repo = SqlVendorRepository(s)
            token = set_tenant_context(TenantContext(tenant_id="t1", request_id="r1"))
            try:
                uc = ModelManagementUseCase(repo)
                await uc.register_vendor(
                    vendor_id="v1", plugin_registration_ref="p1", name="O",
                    config=VendorConfig("openai", "https://api", "h", 1000),
                )
                await uc.register_model(
                    vendor_id="v1", spec=ModelSpec("m1", "gpt", ModelCapability(1000))
                )
                await uc.delete_vendor(vendor_id="v1")

                # 删后查厂商 → 404
                with pytest.raises(BusinessError) as exc:
                    await uc.get_vendor(vendor_id="v1")
                assert exc.value.http_status == 404

                # models 表聚合内行应已随级联清空
                res = await s.execute(text("SELECT COUNT(*) FROM asterism_models WHERE vendor_id='v1'"))
                assert res.scalar() == 0
            finally:
                reset_tenant_context(token)
    finally:
        await engine.dispose()


async def test_management_status_optimistic_lock_conflict_sql():
    engine = await _make_engine()
    try:
        async with AsyncSession(engine, expire_on_commit=False) as s:
            repo = SqlVendorRepository(s)
            token = set_tenant_context(TenantContext(tenant_id="t1", request_id="r1"))
            try:
                uc = ModelManagementUseCase(repo)
                v = await uc.register_vendor(
                    vendor_id="v1", plugin_registration_ref="p1", name="O",
                    config=VendorConfig("openai", "https://api", "h", 1000),
                )
                enabled = await uc.set_vendor_status(
                    vendor_id="v1", status="启用", expected_version=v.version
                )
                assert enabled.status == "启用"

                # 用过时版本号提交 → 乐观锁冲突 409
                with pytest.raises(BusinessError) as exc:
                    await uc.set_vendor_status(
                        vendor_id="v1", status="停用", expected_version=v.version
                    )
                assert exc.value.http_status == 409
                assert exc.value.code == "AST-ERR-3005"
            finally:
                reset_tenant_context(token)
    finally:
        await engine.dispose()


async def test_management_tenant_row_isolation_sql():
    """租户行级隔离：t1 的厂商对 t2 不可见（跨租户查/删均 404）。"""
    engine = await _make_engine()
    try:
        # t1 注册厂商
        async with AsyncSession(engine, expire_on_commit=False) as s1:
            repo1 = SqlVendorRepository(s1)
            token = set_tenant_context(TenantContext(tenant_id="t1", request_id="r1"))
            try:
                uc = ModelManagementUseCase(repo1)
                await uc.register_vendor(
                    vendor_id="v1", plugin_registration_ref="p1", name="O",
                    config=VendorConfig("openai", "https://api", "h", 1000),
                )
            finally:
                reset_tenant_context(token)

        # t2 查/删应 404（行级隔离，TC-12）
        async with AsyncSession(engine, expire_on_commit=False) as s2:
            repo2 = SqlVendorRepository(s2)
            token = set_tenant_context(TenantContext(tenant_id="t2", request_id="r2"))
            try:
                uc2 = ModelManagementUseCase(repo2)
                with pytest.raises(BusinessError) as exc:
                    await uc2.get_vendor(vendor_id="v1")
                assert exc.value.http_status == 404
                with pytest.raises(BusinessError):
                    await uc2.delete_vendor(vendor_id="v1")
            finally:
                reset_tenant_context(token)
    finally:
        await engine.dispose()
