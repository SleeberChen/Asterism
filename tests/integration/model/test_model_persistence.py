"""BC-MODEL 真实持久化集成测试（默认 MySQL 业务库异步 + StubModelAdapter + use_case 端到端）。

验证：DB 仓储落盘 / 新会话边界重载 / 乐观锁(409) / 结构化调用经模板渲染 + 真实端口。
默认目标 = 配置的业务库（异步 MySQL 方言，与 ``DatabaseConfig`` 默认一致；经 db/migration/mysql 落表）。
可用 ``ASTERISM__DATABASE__URL`` 覆盖为 sqlite+aiosqlite 等（仍走版本化迁移）。
每次用例前清空 BC-MODEL 三表，保证用例间不串数据、可重复跑（仅清空 vendors/models/prompt_templates，
不触碰业务库其他 BC 的表）。
全链路异步：引擎为 AsyncEngine，会话为 AsyncSession，所有仓储/服务/用例方法为协程。
每个用例显式关闭会话并 dispose 引擎，避免连接池泄漏告警。
"""

import os

from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from asterism.infrastructure.persistence.db import make_engine, init_db, make_business_engine
from asterism.infrastructure.persistence.model_repository import build_model_repositories
from asterism.domain.model.catalog import (
    VendorConfig,
    ModelSpec,
    ModelCapability,
    PromptTemplate,
    PromptVariable,
    ConcurrencyError,
)
from asterism.domain.model.service import ModelProviderOnboardingService
from asterism.application.model.use_case import ModelInvokeUseCase
from asterism.infrastructure.model.provider import StubModelAdapter
from asterism.domain.model.model import ModelChunk
from asterism.seedwork.context import set_tenant_context, reset_tenant_context, TenantContext


async def _make_engine():
    """默认 MySQL 业务库异步引擎（与 DatabaseConfig 默认一致）；可用 ASTERISM__DATABASE__URL 覆盖。"""
    url = os.environ.get("ASTERISM__DATABASE__URL")
    engine = make_engine(url) if url else make_business_engine()
    await init_db(engine)  # 幂等重放迁移（mysql→db/migration/mysql；sqlite→db/migration/sqlite）
    await _reset_bc_model_tables(engine)  # 清空 BC-MODEL 三表，保证用例可重复跑
    return engine


async def _reset_bc_model_tables(engine):
    """清空 vendors/models/prompt_templates（仅 BC-MODEL 三表），不触碰业务库其他 BC 的表。

    每次用例前调用：vendor_id/template_id 为主键且用例使用固定 ID，必须清空以避免主键冲突。
    """
    dialect = engine.dialect.name
    async with engine.begin() as conn:
        if dialect == "mysql":
            await conn.execute(text("SET FOREIGN_KEY_CHECKS=0"))
            for t in ("asterism_models", "asterism_vendors", "asterism_prompt_templates"):
                await conn.execute(text(f"DELETE FROM {t}"))
            await conn.execute(text("SET FOREIGN_KEY_CHECKS=1"))
        else:  # sqlite / 其他：子表先清，规避外键约束
            await conn.execute(text("DELETE FROM asterism_models"))
            await conn.execute(text("DELETE FROM asterism_vendors"))
            await conn.execute(text("DELETE FROM asterism_prompt_templates"))


def _invoke_repo_bundle(engine):
    """构造 use_case 的每请求模型仓储束（与组合根 ``bootstrap/model._model_repo_bundle`` 同语义）。

    每请求开独立会话并构造 (VendorRepository, PromptTemplateRepository)，退出即关会话，
    数据从 DB 重载（非内存对象）。
    """

    @asynccontextmanager
    async def _cm():
        session = AsyncSession(engine, expire_on_commit=False)
        try:
            yield build_model_repositories(session)
        finally:
            await session.close()

    return _cm


async def test_persistence_round_trip_and_structured_invoke():
    engine = await _make_engine()
    try:
        # 写入侧会话
        async with AsyncSession(engine, expire_on_commit=False) as s1:
            vendors, templates = build_model_repositories(s1)
            onboard = ModelProviderOnboardingService(vendors)
            v = await onboard.register_vendor(
                vendor_id="v1", plugin_registration_ref="p1", name="O",
                config=VendorConfig("openai", "https://api", "handle-x", 1000), tenant_id="t1",
            )
            v.enable()
            await vendors.save(v)
            await onboard.register_model(
                v, ModelSpec("m1", "gpt", ModelCapability(128000, ("text",)), is_default=True)
            )
            tmpl = PromptTemplate(
                "t1", "sys", "你是{{role}}", [PromptVariable("role", default="助手")], tenant_id="t1"
            )
            await templates.save(tmpl)
            await s1.commit()

        # 新会话模拟真实进程边界：数据已从 DB 重载（非内存对象）
        async with AsyncSession(engine, expire_on_commit=False) as s2:
            vendors2, _ = build_model_repositories(s2)
            token = set_tenant_context(TenantContext(tenant_id="t1", request_id="r1"))
            try:
                uc = ModelInvokeUseCase(
                    provider_resolver=lambda _v: StubModelAdapter(),
                    repo_bundle_factory=_invoke_repo_bundle(engine),
                    port=StubModelAdapter(),
                )
                resp = await uc.execute(vendor_id="v1", template_id="t1", var_map={"role": "专家"}, model="default")
            finally:
                reset_tenant_context(token)

        # 结构化路径端到端：默认模型从 DB 解析、租户上下文注入、真实端口被调用
        assert resp.tenant_id == "t1"
        assert resp.model == "m1"  # 默认模型经 DB 解析
        assert resp.text  # 桩适配器给出非空回答（证明端口被调用）
    finally:
        await engine.dispose()


async def test_streaming_invoke_end_to_end_matches_buffered():
    """流式路径经真实 DB 解析 + 模板渲染 + StubModelAdapter 流式端口，末帧 finished=True。

    验证：逐帧拼接 == 缓冲模式完整文本（证明流式与缓冲语义一致），且最后一帧 finished 置位。
    """
    engine = await _make_engine()
    try:
        async with AsyncSession(engine, expire_on_commit=False) as s1:
            vendors, templates = build_model_repositories(s1)
            onboard = ModelProviderOnboardingService(vendors)
            v = await onboard.register_vendor(
                vendor_id="v1", plugin_registration_ref="p1", name="O",
                config=VendorConfig("openai", "https://api", "handle-x", 1000), tenant_id="t1",
            )
            v.enable()
            await vendors.save(v)
            await onboard.register_model(
                v, ModelSpec("m1", "gpt", ModelCapability(128000, ("text",)), is_default=True)
            )
            tmpl = PromptTemplate(
                "t1", "sys", "你是{{role}}", [PromptVariable("role", default="助手")], tenant_id="t1"
            )
            await templates.save(tmpl)
            await s1.commit()

        async with AsyncSession(engine, expire_on_commit=False) as s2:
            vendors2, _ = build_model_repositories(s2)
            token = set_tenant_context(TenantContext(tenant_id="t1", request_id="r-stream"))
            try:
                uc = ModelInvokeUseCase(
                    provider_resolver=lambda _v: StubModelAdapter(),
                    repo_bundle_factory=_invoke_repo_bundle(engine),
                    port=StubModelAdapter(),
                )
                buffered = await uc.execute(vendor_id="v1", template_id="t1", var_map={"role": "专家"}, model="default")
                chunks: list[ModelChunk] = [
                    c
                    async for c in uc.execute_stream(
                        vendor_id="v1", template_id="t1", var_map={"role": "专家"}, model="default"
                    )
                ]
            finally:
                reset_tenant_context(token)

        # 流式拼接 == 缓冲完整文本，语义一致
        assert "".join(c.content for c in chunks) == buffered.text
        # 末帧 finished 置位，其余非末帧
        assert chunks[-1].finished is True
        assert not any(c.finished for c in chunks[:-1])
        # 租户上下文与链路标识透传
        assert all(c.tenant_id == "t1" for c in chunks)
        assert chunks[-1].request_id == "r-stream"
    finally:
        await engine.dispose()


async def test_sql_optimistic_lock_conflict():
    engine = await _make_engine()
    try:
        async with AsyncSession(engine, expire_on_commit=False) as s1:
            vendors, _ = build_model_repositories(s1)
            onboard = ModelProviderOnboardingService(vendors)
            v = await onboard.register_vendor(
                vendor_id="v1", plugin_registration_ref="p1", name="O",
                config=VendorConfig("openai", "https://api", "h", 1000), tenant_id="t1",
            )
            await vendors.save(v)

            a = await vendors.get_by_id("v1", "t1")
            b = await vendors.get_by_id("v1", "t1")
            a.create_model(ModelSpec("ma", "A", ModelCapability(1000)))
            await vendors.save(a)  # 提交：version 1 -> 2
            b.create_model(ModelSpec("mb", "B", ModelCapability(1000)))  # b 仍是 version 1
            try:
                await vendors.save(b)  # 1 != 2 -> 冲突
                assert False, "应触发乐观锁冲突"
            except ConcurrencyError:
                pass
    finally:
        await engine.dispose()


async def test_sql_credential_rotation_replaces_handle():
    engine = await _make_engine()
    try:
        async with AsyncSession(engine, expire_on_commit=False) as s1:
            vendors, _ = build_model_repositories(s1)
            onboard = ModelProviderOnboardingService(vendors)
            v = await onboard.register_vendor(
                vendor_id="v1", plugin_registration_ref="p1", name="O",
                config=VendorConfig("openai", "https://api", "old", 1000), tenant_id="t1",
            )

        async with AsyncSession(engine, expire_on_commit=False) as s2:
            vendors2, _ = build_model_repositories(s2)
            await vendors2.replace_credential_handle("v1", "new-handle", expected_version=1, tenant_id="t1")

            reloaded = await vendors2.get_by_id("v1", "t1")
            assert reloaded.config.credential_handle == "new-handle"
            assert reloaded.config.access_protocol == "openai"  # 其余配置不变
    finally:
        await engine.dispose()


async def test_prompt_template_persistence_round_trip():
    """覆盖 prompt_templates 表 save/get/revise 全链路；验证版本化建表后可持久化。"""
    engine = await _make_engine()
    try:
        # 写入侧会话
        async with AsyncSession(engine, expire_on_commit=False) as s1:
            _, templates = build_model_repositories(s1)
            tmpl = PromptTemplate(
                "t1", "sys", "你是{{role}}", [PromptVariable("role", default="助手")], tenant_id="t1"
            )
            await templates.save(tmpl)
            await s1.commit()

        # 新会话模拟真实进程边界：模板已从 DB 重载（非内存对象）
        async with AsyncSession(engine, expire_on_commit=False) as s2:
            _, templates2 = build_model_repositories(s2)
            reloaded = await templates2.get_by_id("t1", "t1")
            assert reloaded.content == "你是{{role}}"
            assert reloaded.variables[0].name == "role"
            assert reloaded.version == 1

            # 版本化修订后经 DB 持久化，版本递增
            revised = reloaded.revise("你是{{role}}，请专业作答", [PromptVariable("role", default="专家")])
            await templates2.save(revised)
            reloaded2 = await templates2.get_by_id("t1", "t1")
            assert reloaded2.content == "你是{{role}}，请专业作答"
            assert reloaded2.variables[0].default == "专家"
            assert reloaded2.version == 2  # 乐观锁版本由仓储统一递增

        # 验证版本控制：schema_version 已记录成功应用的 V1.0.0
        async with engine.connect() as conn:
            res = await conn.execute(text("SELECT version, success FROM asterism_schema_version"))
            rows = res.fetchall()
        assert ("1.0.0", 1) in [(r[0], r[1]) for r in rows]
    finally:
        await engine.dispose()
