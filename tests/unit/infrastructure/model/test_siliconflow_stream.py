"""SiliconFlowAdapter 流式适配单元测试（无网络 / 无密钥，hermetic）。

验证 ``complete_stream`` 的契约行为：
- 将插件逐片文本包装为领域 ``ModelChunk``，逐片产出、不缓冲；
- 「预读一帧」策略使末帧 ``finished=True``、且仅末帧置位；
- 空流发一帧空内容末帧以宣告完成；
- 插件层 ``ExternalDependencyError`` 透传（4xx / 超时码不丢）；
- 适配器满足 ``StreamingModelPort``（同时具备 complete / complete_stream）。

真实网络流式（SSE 帧格式、逐帧拼接 == 缓冲文本）见 ``scripts/test_siliconflow_invoke.py``。
"""
from __future__ import annotations

from asterism.domain.model.model import ModelRequest
from asterism.domain.model.ports import StreamingModelPort
from asterism.infrastructure.model.siliconflow_provider import SiliconFlowAdapter
from asterism.seedwork.exceptions import ExternalDependencyError


async def _fake_gen(prompt: str, **kwargs) -> object:
    for piece in ["Hello", " world", "!"]:
        yield piece


async def _empty_gen(prompt: str, **kwargs) -> object:
    if False:  # 保持为异步生成器但一帧都不产出
        yield


async def _boom_gen(prompt: str, **kwargs) -> object:
    raise ExternalDependencyError("AST-ERR-4001", message="boom")
    yield  # pragma: no cover - 使函数成为异步生成器


def _req() -> ModelRequest:
    return ModelRequest(tenant_id="t1", prompt="p", model="m1", max_tokens=10)


async def test_adapter_satisfies_streaming_port():
    adapter = SiliconFlowAdapter(base_url="https://x", api_key="k", timeout_s=1.0)
    assert isinstance(adapter, StreamingModelPort)


async def test_adapter_complete_stream_wraps_chunks_and_marks_final():
    adapter = SiliconFlowAdapter(base_url="https://x", api_key="k", timeout_s=1.0)
    adapter._provider.complete_stream = _fake_gen  # 替换插件为内存桩，避免网络

    chunks = [c async for c in adapter.complete_stream(_req())]

    assert len(chunks) == 3
    assert "".join(c.content for c in chunks) == "Hello world!"  # 逐帧拼接 == 完整文本
    assert chunks[-1].finished is True
    assert not any(c.finished for c in chunks[:-1])  # 仅末帧置位
    assert all(c.tenant_id == "t1" and c.model == "m1" for c in chunks)


async def test_adapter_complete_stream_empty_emits_final_frame():
    adapter = SiliconFlowAdapter(base_url="https://x", api_key="k")
    adapter._provider.complete_stream = _empty_gen

    chunks = [c async for c in adapter.complete_stream(_req())]

    assert len(chunks) == 1
    assert chunks[0].content == ""
    assert chunks[0].finished is True


async def test_adapter_complete_stream_propagates_external_error():
    adapter = SiliconFlowAdapter(base_url="https://x", api_key="k")
    adapter._provider.complete_stream = _boom_gen

    with __import__("pytest").raises(ExternalDependencyError) as exc:
        _ = [c async for c in adapter.complete_stream(_req())]
    assert exc.value.code == "AST-ERR-4001"  # 4xx 透传，不丢码
