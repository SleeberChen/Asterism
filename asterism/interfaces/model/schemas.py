"""模型供应接口层请求 / 响应 Schema（Pydantic v2）。"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class ModelInvokeRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=8000, description="提示词文本")
    model: str = Field("default", max_length=64, description="模型标识")
    max_tokens: int = Field(2048, ge=1, le=32768, description="最大生成 token 数")


class ModelInvokeResponse(BaseModel):
    text: str
    tenant_id: str
    model: str
    request_id: Optional[str] = None
