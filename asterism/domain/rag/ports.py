"""RAG 端口（领域层定义，基础设施层实现；依赖倒置，TC-09 / §2.2）。"""

from __future__ import annotations

from typing import List, Protocol, runtime_checkable

from .model import Query, RetrievalResult


@runtime_checkable
class RetrievalPort(Protocol):
    """检索端口：按查询返回相关片段（实现须按 tenant_id 隔离）。"""

    def retrieve(self, query: Query) -> List[RetrievalResult]:
        ...


@runtime_checkable
class GenerationPort(Protocol):
    """生成端口：依据上下文生成回答（实现须经插件内核注册，TC-11）。"""

    def generate(self, query: Query, context: str) -> str:
        ...
