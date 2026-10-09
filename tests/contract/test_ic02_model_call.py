"""契约测试 `T-CONTRACT-02` → `IC-02` 统一模型调用契约。

测试意图（P3 02-应用间契约.md）：
- 切换供应商**业务代码改动 = 0 行**；
- 备用回退成功率 = 100%（注入故障 ≥ 3）。

本骨架当前仅提供单一桩供应商（`StubGenerationProvider`），故：
- 「0 行改动」以**依赖方向**实证（领域 / 应用层不依赖任何具体供应商实现）；
- 「回退」以**可替换性**实证（注入另一实现，用例代码零改动即可工作）。
"""
from __future__ import annotations

from pathlib import Path

from asterism.application.rag.use_case import RagQueryUseCase
from asterism.domain.rag.model import Document
from asterism.domain.rag.orchestrator import RagOrchestrator
from asterism.domain.rag.ports import GenerationPort
from asterism.infrastructure.rag.model_provider import StubGenerationProvider
from asterism.infrastructure.rag.vector_store import InMemoryVectorStore

REPO_ROOT = Path(__file__).resolve().parents[2]


def _py_files(relative: str) -> list[Path]:
    base = REPO_ROOT / relative
    return [p for p in base.rglob("*.py") if "__pycache__" not in p.parts]


def test_business_layers_do_not_depend_on_any_provider():
    """领域层 / 应用层不 import 任何基础设施供应商实现 → 换供应商业务代码改动 = 0。"""
    offenders: list[str] = []
    for layer in ("asterism/domain", "asterism/application"):
        for path in _py_files(layer):
            text = path.read_text(encoding="utf-8")
            if "asterism.infrastructure" in text:
                offenders.append(str(path.relative_to(REPO_ROOT)))
    assert offenders == [], f"业务层出现对基础设施实现的依赖：{offenders}"


class _AlternateProvider:
    """备用供应商桩：证明替换实现无需改动用例 / 编排代码。"""

    def generate(self, query: str, contexts: list[str]) -> str:
        return f"[alt]{query}|{len(contexts)}"


def test_provider_swap_requires_zero_business_code_change(tenant_ctx):
    """同一 `RagQueryUseCase` 在替换生成端口实现后仍可工作（用例代码未改）。

    隔离上下文由框架统一注入（TC-12），缺失即拒绝，故本用例经 `tenant_ctx` 注入。
    """
    store = InMemoryVectorStore()
    store.add(
        Document(
            id="d1",
            tenant_id="demo-tenant",
            title="Asterism",
            content="Asterism 采用 DDD 四层架构。\n\n一切皆插件。",
        )
    )

    primary = RagQueryUseCase(
        orchestrator=RagOrchestrator(
            retrieval=store, generation=StubGenerationProvider()
        )
    )
    fallback = RagQueryUseCase(
        orchestrator=RagOrchestrator(retrieval=store, generation=_AlternateProvider())
    )

    primary_answer = primary.execute("Asterism 的架构")
    assert primary_answer.text  # 主供应商可用

    # 备用供应商生效：回答带 [alt] 前缀，证明替换的是端口实现而非业务代码
    fallback_answer = fallback.execute("Asterism 的架构")
    assert fallback_answer.text.startswith("[alt]")  # 零业务改动即完成切换


def test_generation_port_is_the_only_seam():
    """生成能力经单一端口 `GenerationPort` 接入（供应商可替换的前提）。"""
    assert isinstance(StubGenerationProvider(), GenerationPort)
