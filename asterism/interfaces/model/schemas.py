"""模型供应接口层请求 / 响应 Schema（Pydantic v2）。"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class ModelInvokeRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=8000, description="提示词文本")
    model: str = Field("default", max_length=64, description="模型标识")
    max_tokens: int = Field(2048, ge=1, le=32768, description="最大生成 token 数")
    vendor_id: Optional[str] = Field(
        "siliconflow", max_length=64, description="结构化路径厂商 ID（默认硅基流动）"
    )


class ModelInvokeResponse(BaseModel):
    text: str
    tenant_id: str
    model: str
    request_id: Optional[str] = None


class ModelStreamRequest(BaseModel):
    """流式调用请求：字段与 ``ModelInvokeRequest`` 对齐，并补充结构化路径可选参数。"""

    prompt: str = Field(..., min_length=1, max_length=8000, description="提示词文本")
    model: str = Field("default", max_length=64, description="模型标识")
    max_tokens: int = Field(2048, ge=1, le=32768, description="最大生成 token 数")
    vendor_id: Optional[str] = Field(
        "siliconflow", max_length=64, description="结构化路径：厂商 ID（默认硅基流动）"
    )
    template_id: Optional[str] = Field(None, max_length=64, description="结构化路径：提示词模板 ID")
    var_map: Optional[dict[str, str]] = Field(None, description="模板变量映射")


class ModelChunkResponse(BaseModel):
    """流式输出单帧（SSE data 荷载）。"""

    content: str
    tenant_id: str
    model: str
    request_id: Optional[str] = None
    finished: bool = False
