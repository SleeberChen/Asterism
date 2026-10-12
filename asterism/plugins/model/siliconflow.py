"""硅基流动（SiliconFlow）OpenAI 兼容模型供应商插件（真实调用，生产替换桩）。

真实供应商接入遵循「一切皆插件」：实现 ``ModelProvider`` 并经内核 / 协议注册表登记；
业务编排（``UnifiedModelInvocationService``）仅依赖 ``ModelPort`` 契约，不感知具体供应商。

同步 ``complete`` 保留插件契约签名；真实生成在 ``chat``（异步）完成，由适配器 ``SiliconFlowAdapter``
调用——因模型生成必须是异步（不阻塞事件循环）。
"""
from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

from asterism.plugins.kernel.base import PluginKind
from asterism.seedwork.exceptions import ExternalDependencyError

from .base import ModelProvider


class SiliconFlowProvider(ModelProvider):
    """硅基流动 OpenAI 兼容供应商（chat/completions 端点）。"""

    name = "siliconflow"
    kind = PluginKind.MODEL

    def complete(self, prompt: str, **kwargs: Any) -> str:  # pragma: no cover - 经适配器异步调用
        raise NotImplementedError("SiliconFlowProvider 仅经 SiliconFlowAdapter 异步调用")

    async def complete_stream(self, prompt: str, **kwargs: Any) -> AsyncIterator[str]:
        """插件级流式入口：委托 ``chat_stream`` 真实流式生成。

        适配器 ``SiliconFlowAdapter`` 持有凭据，经本方法传入（与 ``chat`` 同口径）；
        业务编排不感知具体供应商（一切皆插件）。
        """
        async for piece in self.chat_stream(
            api_key=kwargs["api_key"],
            base_url=kwargs["base_url"],
            model=kwargs["model"],
            prompt=prompt,
            max_tokens=kwargs.get("max_tokens", 2048),
            timeout_s=kwargs.get("timeout_s", 60.0),
        ):
            yield piece

    async def chat(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        prompt: str,
        max_tokens: int,
        timeout_s: float = 60.0,
    ) -> str:
        """真实调用 SiliconFlow OpenAI 兼容 ``/chat/completions``，返回生成文本。

        失败统一映射为 ``ExternalDependencyError``（4xx 透传，AST-ERR-4001/4002），
        由上层决定回退（ADR-008），禁止编造内容。
        """
        import httpx

        url = f"{base_url.rstrip('/')}/chat/completions"
        try:
            async with httpx.AsyncClient(timeout=timeout_s) as client:
                resp = await client.post(
                    url,
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": model,
                        "messages": [{"role": "user", "content": prompt}],
                        "max_tokens": max_tokens,
                        "stream": False,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                return data["choices"][0]["message"]["content"]
        except httpx.TimeoutException as exc:
            raise ExternalDependencyError(
                "AST-ERR-4002", message="模型调用超时", cause=exc
            ) from exc
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code if exc.response is not None else "?"
            raise ExternalDependencyError(
                "AST-ERR-4001", message=f"模型供应商返回 {status}", cause=exc
            ) from exc
        except Exception as exc:
            raise ExternalDependencyError(
                "AST-ERR-4001", message="模型生成失败", cause=exc
            ) from exc

    async def chat_stream(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        prompt: str,
        max_tokens: int,
        timeout_s: float = 60.0,
    ) -> AsyncIterator[str]:
        """真实流式调用 SiliconFlow OpenAI 兼容 ``/chat/completions``（stream=True），
        逐片 yield 文本。

        直接消费 SSE 流（不缓冲完整响应），逐片产出
        ``choices[0].delta.content``；遇 ``data: [DONE]`` 或流结束即停止。
        失败统一映射为 ``ExternalDependencyError``（4xx 透传，AST-ERR-4001/4002），
        由上层决定回退（ADR-008），禁止编造内容。
        """
        import httpx

        url = f"{base_url.rstrip('/')}/chat/completions"
        try:
            async with httpx.AsyncClient(timeout=timeout_s) as client:
                async with client.stream(
                    "POST",
                    url,
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                        "Accept": "text/event-stream",
                    },
                    json={
                        "model": model,
                        "messages": [{"role": "user", "content": prompt}],
                        "max_tokens": max_tokens,
                        "stream": True,
                    },
                ) as resp:
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        if not line or not line.startswith("data:"):
                            continue
                        payload = line[len("data:"):].strip()
                        if not payload or payload == "[DONE]":
                            continue
                        try:
                            data = json.loads(payload)
                        except json.JSONDecodeError:
                            # 偶发无法解析的片段（如心跳 / 注释行）：跳过，不中断流
                            continue
                        # 流内错误（部分供应商在 data 帧内返回 error 字段而不关闭连接）
                        if isinstance(data, dict) and data.get("error"):
                            raise ExternalDependencyError(
                                "AST-ERR-4001", message=f"模型供应商流内错误: {data['error']}"
                            )
                        for choice in data.get("choices", []):
                            delta = choice.get("delta") or {}
                            piece = delta.get("content")
                            if piece:
                                yield piece
        except httpx.TimeoutException as exc:
            raise ExternalDependencyError(
                "AST-ERR-4002", message="模型调用超时", cause=exc
            ) from exc
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code if exc.response is not None else "?"
            raise ExternalDependencyError(
                "AST-ERR-4001", message=f"模型供应商返回 {status}", cause=exc
            ) from exc
        except ExternalDependencyError:
            raise  # 4xx 透传
        except Exception as exc:
            raise ExternalDependencyError(
                "AST-ERR-4001", message="模型流式生成失败", cause=exc
            ) from exc
