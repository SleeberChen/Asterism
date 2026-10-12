"""模型流式调用端到端测试（真实 ASGI 应用 + SSE 逐帧）。

覆盖 ``POST /api/v1/models/invoke/stream`` 经真实 ASGI 链路（鉴权头解析 → 隔离上下文注入
→ 用例 → 端口 → SSE 响应）的完整行为：

- SSE 帧格式与末帧 ``finished``；
- 逐帧拼接与缓冲模式一致；
- **流式收尾时隔离上下文复位不跨 Context 抛错**（流式响应体在独立 task 中运行，
  其 context 是入口 context 的副本，在生成器里 reset 入口 token 会触发
  ``ValueError: ... was created in a different Context``）。

环境约定（TC-21）：依赖 ``starlette.testclient``（随 fastapi 安装），缺失即失败而非跳过。
"""

from __future__ import annotations

import json

import pytest

# 直接导入：若 TestClient 不可用，收集即失败（符合 TC-21「环境不可用判失败」）。
from fastapi.testclient import TestClient

from asterism.main import create_app


@pytest.fixture
def client():
    """按运行形态独立部署入口构建应用；TestClient 上下文触发 lifespan。"""
    app = create_app()
    with TestClient(app) as c:
        yield c


def _parse_sse(body: str):
    """解析 SSE 文本为 data 荷载字典列表（忽略事件名行与空帧）。"""
    out = []
    for frame in body.split("\n\n"):
        frame = frame.strip()
        if not frame:
            continue
        for line in frame.splitlines():
            if line.startswith("data: "):
                out.append(json.loads(line[len("data: ") :]))
    return out


def test_stream_requires_tenant_header(client):
    """缺失 X-Tenant-Id 头 → 401（隔离上下文在边缘强制注入，TC-12）。"""
    resp = client.post("/api/v1/models/invoke/stream", json={"prompt": "你好"})
    assert resp.status_code == 401


def test_stream_returns_sse_frames_with_final_flag(client):
    """流式链路返回 SSE 帧序列，末帧 finished=True，且租户上下文透传。"""
    with client.stream(
        "POST",
        "/api/v1/models/invoke/stream",
        json={"prompt": "你好"},
        headers={"X-Tenant-Id": "t-stream"},
    ) as resp:
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        body = "".join(resp.iter_text())

    frames = _parse_sse(body)
    assert frames, "应至少产生一帧 SSE 数据"
    # 每帧包裹统一信封：业务负载在 data 内
    assert all(f["data"]["tenant_id"] == "t-stream" for f in frames)
    assert frames[-1]["data"]["finished"] is True
    assert not any(f["data"]["finished"] for f in frames[:-1])  # 仅末帧置位
    assert "".join(f["data"]["content"] for f in frames)  # 内容非空


def test_stream_content_matches_buffered_invoke(client):
    """流式逐帧拼接 == 缓冲模式完整文本（两种模式语义一致）。"""
    buffered = client.post(
        "/api/v1/models/invoke",
        json={"prompt": "你好"},
        headers={"X-Tenant-Id": "t-stream"},
    )
    assert buffered.status_code == 200

    with client.stream(
        "POST",
        "/api/v1/models/invoke/stream",
        json={"prompt": "你好"},
        headers={"X-Tenant-Id": "t-stream"},
    ) as resp:
        assert resp.status_code == 200
        body = "".join(resp.iter_text())

    streamed = "".join(f["data"]["content"] for f in _parse_sse(body))
    assert streamed == buffered.json()["data"]["text"]


def test_stream_does_not_leak_tenant_context_after_streaming(client):
    """流式结束后不应把隔离上下文泄漏到后续请求（复位不跨 Context 抛错）。

    连续两次流式调用均须成功；若生成器内复位跨 Context，第二次/首次即会 500。
    """
    for _ in range(2):
        with client.stream(
            "POST",
            "/api/v1/models/invoke/stream",
            json={"prompt": "上下文复位"},
            headers={"X-Tenant-Id": "t-stream"},
        ) as resp:
            assert resp.status_code == 200
            body = "".join(resp.iter_text())
        assert _parse_sse(body), "每轮均应产生 SSE 帧"

    # 未带隔离头的请求仍应被边缘拒绝（证明上下文未泄漏为「已注入」状态）
    assert client.post("/api/v1/models/invoke/stream", json={"prompt": "x"}).status_code == 401
