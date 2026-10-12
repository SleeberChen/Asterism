"""硅基流动（SiliconFlow）OpenAI 兼容模型供应商插件（真实调用，生产替换桩）。

真实供应商接入遵循「一切皆插件」：实现 ``ModelProvider`` 并经内核 / 协议注册表登记；
业务编排（``UnifiedModelInvocationService``）仅依赖 ``ModelPort`` 契约，不感知具体供应商。

同步 ``complete`` 保留插件契约签名；真实生成在 ``chat``（异步）完成，由适配器 ``SiliconFlowAdapter``
调用——因模型生成必须是异步（不阻塞事件循环）。
"""
from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from asterism.plugins.kernel.base import PluginKind
from .base import ModelProvider
from asterism.seedwork.exceptions import ExternalDependencyError


class SiliconFlowProvider(ModelProvider):
    """硅基流动 OpenAI 兼容供应商（chat/completions 端点）。"""

    name = "siliconflow"
    kind = PluginKind.MODEL

    def complete(self, prompt: str, **kwargs: Any) -> str:  # pragma: no cover - 经适配器异步调用
        raise NotImplementedError("SiliconFlowProvider 仅经 SiliconFlowAdapter 异步调用")

    async def complete_stream(self, prompt: str, **kwargs: Any) -> AsyncIterator[str]:  # pragma: no cover
        raise NotImplementedError

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
            raise ExternalDependencyError("AST-ERR-4002", message="模型调用超时", cause=exc) from exc
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code if exc.response is not None else "?"
            raise ExternalDependencyError(
                "AST-ERR-4001", message=f"模型供应商返回 {status}", cause=exc
            ) from exc
        except Exception as exc:
            raise ExternalDependencyError("AST-ERR-4001", message="模型生成失败", cause=exc) from exc
