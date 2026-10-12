"""BC-MODEL 领域聚合单元测试（Option A + 提示词模板草稿）。

覆盖：值对象不可变/校验、聚合不变量 IN10/IN11/IN12、模板渲染、仓储乐观锁(409)、
供应商入驻 + 建模型 + 调用 happy path（含模板渲染）、回退。无 IO / 无框架依赖。
仓储与服务方法为协程（全链路异步），相关用例用 async def + await。
"""
from asterism.domain.model.catalog import (
    Vendor,
    VendorConfig,
    ModelSpec,
    ModelCapability,
    PromptTemplate,
    PromptVariable,
    InvariantViolationError,
    ConcurrencyError,
    TemplateRenderError,
    NotFoundError,
)
from asterism.domain.model.repository import VendorRepository, PromptTemplateRepository
from asterism.domain.model.service import (
    ModelProviderOnboardingService,
    UnifiedModelInvocationService,
    ModelFailoverService,
)
from asterism.domain.model.ports import ModelPort
from asterism.domain.model.model import ModelChunk, ModelResponse
from asterism.application.model.use_case import ModelInvokeUseCase
from asterism.seedwork.context import TenantContext, reset_tenant_context, set_tenant_context


# ---------------------------------------------------------------------------
# 值对象（纯领域，无 IO）
# ---------------------------------------------------------------------------
def test_vendor_config_rejects_empty_credential():
    try:
        VendorConfig("openai", "https://api", "", 1000)
        assert False, "应拒绝空凭据句柄"
    except InvariantViolationError:
        pass


def test_vendor_config_frozen():
    cfg = VendorConfig("openai", "https://api", "handle-x", 1000)
    try:
        cfg.credential_handle = "other"
        assert False, "VO 应不可变"
    except Exception:
        pass


def test_model_capability_summary():
    cap = ModelCapability(context_window=128000, modalities=("text", "vision"))
    assert cap.summary() == "ctx=128000;mod=text,vision"


# ---------------------------------------------------------------------------
# 聚合不变量（纯领域，无 IO）
# ---------------------------------------------------------------------------
def test_vendor_create_model_default_unique():
    v = Vendor("v1", "p1", "O", VendorConfig("openai", "https://api", "h", 1000), tenant_id="t1")
    v.create_model(ModelSpec("m1", "M1", ModelCapability(1000), is_default=True))
    try:
        v.create_model(ModelSpec("m2", "M2", ModelCapability(1000), is_default=True))
        assert False, "第二个默认模型应被拒（IN11）"
    except InvariantViolationError:
        pass


def test_vendor_rotate_credentials_replaces_config():
    v = Vendor("v1", "p1", "O", VendorConfig("openai", "https://api", "old", 1000), tenant_id="t1")
    v.rotate_credentials("new-handle")
    assert v.config.credential_handle == "new-handle"
    assert v.config.access_protocol == "openai"


# ---------------------------------------------------------------------------
# 提示词模板（纯领域，无 IO）
# ---------------------------------------------------------------------------
def test_template_render_with_default():
    t = PromptTemplate(
        "t1",
        "greet",
        "你好 {{name}}，上限 {{limit}}",
        [PromptVariable("name"), PromptVariable("limit", default="128k")],
        tenant_id="t1",
    )
    assert t.render({"name": "A"}) == "你好 A，上限 128k"


def test_template_render_raises_when_no_value_no_default():
    t = PromptTemplate("t1", "g", "你好 {{name}}", [PromptVariable("name")], tenant_id="t1")
    try:
        t.render({})
        assert False, "无值无默认应拒绝"
    except TemplateRenderError:
        pass


async def test_template_revision_bumps_version_via_repo():
    repo = PromptTemplateRepository()
    t = PromptTemplate(
        "t1", "g", "v1 {{x}}", [PromptVariable("x", default="1")], tenant_id="t1"
    )
    await repo.save(t)
    loaded = await repo.get_by_id("t1", "t1")
    revised = loaded.revise("v2 {{x}}", [PromptVariable("x", default="2")])
    await repo.save(revised)
    assert (await repo.get_by_id("t1", "t1")).version == 2
    assert (await repo.get_by_id("t1", "t1")).content == "v2 {{x}}"


# ---------------------------------------------------------------------------
# 仓储乐观锁（异步）
# ---------------------------------------------------------------------------
async def test_vendor_repo_optimistic_lock_conflict():
    repo = VendorRepository()
    onboard = ModelProviderOnboardingService(repo)
    await onboard.register_vendor(
        vendor_id="v1", plugin_registration_ref="p1", name="O",
        config=VendorConfig("openai", "https://api", "h", 1000), tenant_id="t1",
    )
    # 两个独立加载（副本）
    a = await repo.get_by_id("v1", "t1")
    b = await repo.get_by_id("v1", "t1")
    a.create_model(ModelSpec("ma", "A", ModelCapability(1000)))
    await repo.save(a)  # 提交：version 1 -> 2
    b.create_model(ModelSpec("mb", "B", ModelCapability(1000)))  # b 仍是 version 1
    try:
        await repo.save(b)  # 1 != 2 -> 冲突
        assert False, "应触发乐观锁冲突"
    except ConcurrencyError:
        pass


# ---------------------------------------------------------------------------
# 入驻 + 建模型 + 调用 happy path（异步）
# ---------------------------------------------------------------------------
class _FakePort:
    async def complete(self, request):
        return ModelResponse(text="ok:" + request.prompt, tenant_id=request.tenant_id, model=request.model)

    async def complete_stream(self, request):
        # 演示流式：把完整文本拆成两帧，末帧 finished=True
        full = "ok:" + request.prompt
        mid = len(full) // 2
        yield ModelChunk(content=full[:mid], tenant_id=request.tenant_id, model=request.model)
        yield ModelChunk(content=full[mid:], tenant_id=request.tenant_id, model=request.model, finished=True)


async def test_execute_stream_direct_path_marks_final_chunk():
    token = set_tenant_context(TenantContext(tenant_id="t1", request_id="r9"))
    try:
        uc = ModelInvokeUseCase(_FakePort())
        chunks = [c async for c in uc.execute_stream("你好", request_id="r9", model="default")]
    finally:
        reset_tenant_context(token)
    assert len(chunks) == 2
    assert "".join(c.content for c in chunks) == "ok:你好"
    assert all(c.request_id == "r9" for c in chunks)  # 用例层回填 request_id
    assert chunks[-1].finished is True
    assert not any(c.finished for c in chunks[:-1])


class _FakeNonStreamingPort:
    """仅实现 ``complete``（无 ``complete_stream``），用于验证可选流式能力的回退。"""

    async def complete(self, request):
        return ModelResponse(text="buf:" + request.prompt, tenant_id=request.tenant_id, model=request.model)


async def test_execute_stream_falls_back_to_buffered_when_port_not_streaming():
    token = set_tenant_context(TenantContext(tenant_id="t1", request_id="r10"))
    try:
        uc = ModelInvokeUseCase(_FakeNonStreamingPort())
        chunks = [c async for c in uc.execute_stream("hi", request_id="r10")]
    finally:
        reset_tenant_context(token)
    # 回退：单帧 finished=True，内容为完整缓冲文本
    assert len(chunks) == 1
    assert chunks[0].content == "buf:hi"
    assert chunks[0].finished is True
    assert chunks[0].request_id == "r10"


async def test_onboard_create_model_and_invoke_with_template():
    vendors = VendorRepository()
    templates = PromptTemplateRepository()
    onboard = ModelProviderOnboardingService(vendors)
    invoker = UnifiedModelInvocationService(vendors, templates, _FakePort())

    v = await onboard.register_vendor(
        vendor_id="v1", plugin_registration_ref="p1", name="O",
        config=VendorConfig("openai", "https://api", "h", 1000), tenant_id="t1",
    )
    v.enable()
    await vendors.save(v)
    evt = await onboard.register_model(
        v, ModelSpec("m1", "gpt", ModelCapability(128000, ("text",)), is_default=True)
    )
    assert evt.type == "EVT-MODEL-REGISTERED"
    assert evt.model_name == "gpt"

    tmpl = PromptTemplate(
        "t1", "sys", "你是{{role}}，上限{{limit}}",
        [PromptVariable("role"), PromptVariable("limit", default="128k")], tenant_id="t1",
    )
    await templates.save(tmpl)

    result = await invoker.call(
        tenant_id="t1", vendor_id="v1", model_id="default",
        template_id="t1", var_map={"role": "助手"},
    )
    assert result.text == "ok:你是助手，上限128k"
    assert result.fallback is False
    assert result.actual_model_id == "m1"


async def test_call_stream_structured_yields_chunks():
    vendors = VendorRepository()
    templates = PromptTemplateRepository()
    onboard = ModelProviderOnboardingService(vendors)
    invoker = UnifiedModelInvocationService(vendors, templates, _FakePort())

    v = await onboard.register_vendor(
        vendor_id="v1", plugin_registration_ref="p1", name="O",
        config=VendorConfig("openai", "https://api", "h", 1000), tenant_id="t1",
    )
    v.enable()
    await vendors.save(v)
    await onboard.register_model(
        v, ModelSpec("m1", "gpt", ModelCapability(128000, ("text",)), is_default=True)
    )
    tmpl = PromptTemplate(
        "t1", "sys", "你是{{role}}，上限{{limit}}",
        [PromptVariable("role"), PromptVariable("limit", default="128k")], tenant_id="t1",
    )
    await templates.save(tmpl)

    chunks = [
        c
        async for c in invoker.call_stream(
            tenant_id="t1", vendor_id="v1", model_id="default",
            template_id="t1", var_map={"role": "助手"},
        )
    ]
    assert "".join(c.content for c in chunks) == "ok:你是助手，上限128k"
    assert chunks[-1].finished is True


async def test_invoke_rejects_when_no_default_and_no_model():
    vendors = VendorRepository()
    onboard = ModelProviderOnboardingService(vendors)
    v = await onboard.register_vendor(
        vendor_id="v1", plugin_registration_ref="p1", name="O",
        config=VendorConfig("openai", "https://api", "h", 1000), tenant_id="t1",
    )
    invoker = UnifiedModelInvocationService(vendors, PromptTemplateRepository(), _FakePort())
    try:
        await invoker.call(tenant_id="t1", vendor_id="v1", model_id="default")
        assert False, "无默认模型应拒绝"
    except InvariantViolationError:
        pass


# ---------------------------------------------------------------------------
# 回退（异步）
# ---------------------------------------------------------------------------
async def test_failover_returns_target_and_event():
    vendors = VendorRepository()
    onboard = ModelProviderOnboardingService(vendors)
    v1 = await onboard.register_vendor(
        vendor_id="v1", plugin_registration_ref="p1", name="O1",
        config=VendorConfig("openai", "https://api", "h", 1000), tenant_id="t1",
    )
    v2 = await onboard.register_vendor(
        vendor_id="v2", plugin_registration_ref="p2", name="O2",
        config=VendorConfig("azure", "https://api", "h", 1000), tenant_id="t1",
    )
    v1.enable(); v2.enable()
    await vendors.save(v1); await vendors.save(v2)
    target, evt = await ModelFailoverService(vendors).failover(
        failed_vendor_id="v1", tenant_id="t1", reason="timeout"
    )
    assert target.vendor_id == "v2"
    assert evt.type == "EVT-MODEL-FAILOVER"


async def test_failover_explicit_failure_when_no_candidate():
    vendors = VendorRepository()
    onboard = ModelProviderOnboardingService(vendors)
    v1 = await onboard.register_vendor(
        vendor_id="v1", plugin_registration_ref="p1", name="O1",
        config=VendorConfig("openai", "https://api", "h", 1000), tenant_id="t1",
    )
    # v1 停用，无其他启用厂商
    fs = ModelFailoverService(vendors)
    try:
        await fs.failover(failed_vendor_id="v1", tenant_id="t1", reason="down")
        assert False, "无候选应显式失败"
    except InvariantViolationError:
        pass
