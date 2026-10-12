"""端到端验证：以「硅基流动」为默认供应商真实调用 /invoke。

合规要点：
- 真实 API 秘钥只从运行环境 ``SILICONFLOW_API_KEY`` 读取（调用脚本时通过环境变量注入），
  本脚本不硬编码、不落库（库内仅存 ``env://SILICONFLOW_API_KEY`` 引用）。
- 业务库复用 seed 脚本写入的 ``scripts/seed_business.db``（厂商 siliconflow / 模型 GLM-Z1-9B-0414）。

运行：
    SILICONFLOW_API_KEY="sk-..." uv run python scripts/test_siliconflow_invoke.py

验证四项（缓冲 + 流式各一成功一失败）：
1) 缓冲成功：真实 key → /invoke 返回模型生成文本（证明默认供应商接线正确）。
2) 流式成功：真实 key → /invoke/stream 逐帧返回 ModelChunk，末帧 finished=True，
   逐帧拼接 == 缓冲文本（SSE 契约）。
3) 缓冲失败：key 临时改为伪造值 → 供应商 4xx → 映射 AST-ERR-4001（HTTP 502）。
4) 流式失败：伪造 key → /invoke/stream 推 ``event: error`` 帧，码 AST-ERR-4001。
"""

from __future__ import annotations

import json
import os
from pathlib import Path

# 必须在导入 asterism 之前确定业务库（引擎懒加载时读取 ASTERISM__DATABASE__URL）
SEED_DB = (Path(__file__).resolve().parent / "seed_business.db").as_posix()
os.environ.setdefault("ASTERISM__DATABASE__URL", f"sqlite+aiosqlite:///{SEED_DB}")

from fastapi.testclient import TestClient  # noqa: E402

from asterism.main import create_app  # noqa: E402

TENANT = "t-default"
HEADERS = {"X-Tenant-Id": TENANT, "X-User-Id": "admin"}


def _enable_vendor_if_needed(c: TestClient) -> None:
    r = c.get("/api/v1/models/vendors/siliconflow", headers=HEADERS)
    if r.status_code != 200:
        print(f"[WARN] 读取厂商失败: {r.status_code} {r.text}")
        return
    data = r.json()["data"]
    print(f"[现状] vendor=siliconflow status={data['status']} version={data['version']}")
    if data["status"] != "启用":
        r2 = c.put(
            "/api/v1/models/vendors/siliconflow/status",
            headers=HEADERS,
            json={"status": "启用", "expected_version": data["version"]},
        )
        print(f"[启用] PUT status -> {r2.status_code} {r2.text}")
    else:
        print("[启用] 已是启用状态，跳过")


def _invoke(c: TestClient, prompt: str) -> dict:
    r = c.post(
        "/api/v1/models/invoke",
        headers=HEADERS,
        json={"prompt": prompt, "vendor_id": "siliconflow", "model": "default"},
    )
    return {"status": r.status_code, "body": r.json()}


def _parse_sse(body: str) -> list[dict]:
    """解析 SSE 文本为帧列表；成功帧 event=None，错误帧 event='error'。"""
    frames: list[dict] = []
    for frame in body.split("\n\n"):
        frame = frame.strip()
        if not frame:
            continue
        event = None
        data = None
        for line in frame.splitlines():
            if line.startswith("event: "):
                event = line[len("event: "):].strip()
            elif line.startswith("data: "):
                data = json.loads(line[len("data: "):])
        if data is not None:
            frames.append({"event": event, "data": data})
    return frames


def _invoke_stream(c: TestClient, prompt: str) -> dict:
    with c.stream(
        "POST",
        "/api/v1/models/invoke/stream",
        headers=HEADERS,
        json={"prompt": prompt, "vendor_id": "siliconflow", "model": "default"},
    ) as r:
        status = r.status_code
        body = "".join(r.iter_text())
    return {"status": status, "body": body, "frames": _parse_sse(body)}


def main() -> int:
    key = os.environ.get("SILICONFLOW_API_KEY")
    if not key:
        print("[FATAL] 未设置环境变量 SILICONFLOW_API_KEY（真实 key 须运行时注入，不落文件）")
        return 2

    app = create_app()
    with TestClient(app) as c:
        _enable_vendor_if_needed(c)

        # --- 1) 缓冲成功路径：真实 key ---
        print("\n=== 缓冲成功路径（真实 key）===")
        res = _invoke(c, "用一句话向中学生解释量子计算。")
        print("HTTP", res["status"])
        print(json.dumps(res["body"], ensure_ascii=False, indent=2))
        ok = res["status"] == 200 and res["body"].get("code") == "0" and res["body"]["data"]["text"]
        print("结果:", "成功 ✅" if ok else "失败 ❌")

        # --- 1b) 流式成功路径：真实 key（逐帧 + 末帧 finished）---
        print("\n=== 流式成功路径（真实 key）===")
        res_s = _invoke_stream(c, "用一句话向中学生解释量子计算。")
        print("HTTP", res_s["status"])
        data_frames = [f for f in res_s["frames"] if f["event"] is None]
        stream_text = "".join(f["data"]["content"] for f in data_frames)
        last_finished = data_frames[-1]["data"]["finished"] if data_frames else None
        print(f"帧数={len(data_frames)} 末帧finished={last_finished} 拼接长度={len(stream_text)}")
        ok_stream = (
            res_s["status"] == 200
            and bool(data_frames)
            and last_finished is True
            and not any(f["data"]["finished"] for f in data_frames[:-1])
            and stream_text == res["body"]["data"]["text"]  # 流式拼接 == 缓冲文本
        )
        print("结果:", "成功 ✅" if ok_stream else "失败 ❌")

        # --- 2) 缓冲失败路径：伪造 key（验证 4xx → AST-ERR-4001 映射）---
        print("\n=== 缓冲失败路径（伪造 key）===")
        os.environ["SILICONFLOW_API_KEY"] = "sk-" + "x" * 32  # 仅本次进程内临时替换
        res2 = _invoke(c, "hello")
        print("HTTP", res2["status"])
        print(json.dumps(res2["body"], ensure_ascii=False, indent=2))
        err_ok = res2["body"].get("code") == "AST-ERR-4001"
        print("结果:", "失败映射正确 ✅ (AST-ERR-4001)" if err_ok else "失败映射异常 ❌")

        # --- 2b) 流式失败路径：伪造 key（event: error 帧 + AST-ERR-4001）---
        print("\n=== 流式失败路径（伪造 key）===")
        res2s = _invoke_stream(c, "hello")
        print("HTTP", res2s["status"])
        err_frames = [f for f in res2s["frames"] if f["event"] == "error"]
        err_ok_stream = bool(err_frames) and err_frames[0]["data"].get("code") == "AST-ERR-4001"
        if err_frames:
            print("错误帧:", json.dumps(err_frames[0]["data"], ensure_ascii=False))
        print("结果:", "失败映射正确 ✅ (AST-ERR-4001)" if err_ok_stream else "失败映射异常 ❌")

    all_ok = ok and ok_stream and err_ok and err_ok_stream
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
