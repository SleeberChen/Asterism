"""桩模型供应商（演示 / 测试用，避免真实密钥与网络，TC-01）。

真实供应商接入时新增 ``plugins.model.<vendor>`` 实现 ``ModelProvider`` 并经内核注册；
业务侧仅依赖 ``ModelProvider.complete`` 契约，不感知具体供应商（ADR-008 回退）。
"""

from __future__ import annotations

from asterism.plugins.kernel.base import PluginKind
from .base import ModelProvider


class StubModelProvider(ModelProvider):
    """确定性桩实现：从提示词中提取上下文片段并生成可复核的回答。"""

    name = "stub"

    def complete(self, prompt: str, **kwargs: object) -> str:
        # 演示：从提示词中的 [CONTEXT] 段提取检索到的片段，拼接成回答
        ctx_marker = "[CONTEXT]"
        answer_marker = "[ANSWER]"
        if ctx_marker in prompt:
            context = prompt.split(ctx_marker, 1)[1].split(answer_marker, 1)[0].strip()
            snippet = context[:120]
            return (
                f"根据已检索资料：{snippet}……（由 stub 模型生成；"
                f"生产环境应替换为真实供应商并完成密钥托管 TC-02）"
            )
        return "（stub 模型：未提供上下文，返回占位回答）"
