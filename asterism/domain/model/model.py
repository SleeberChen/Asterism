"""模型供应领域模型（纯数据，无 IO、无框架依赖）。

**分层建模规范**：领域层实体 / 值对象用 ``dataclass``，不引入 Pydantic（保持领域纯净）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class ModelRequest:
    """模型调用请求（隔离维度来自框架注入的上下文，TC-12）。"""

    tenant_id: str
    prompt: str
    model: str = "default"
    max_tokens: int = 2048


@dataclass
class ModelResponse:
    """模型调用响应。"""

    text: str
    tenant_id: str
    model: str
    request_id: Optional[str] = None
