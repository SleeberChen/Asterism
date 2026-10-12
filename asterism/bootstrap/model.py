"""APP-MODEL 装配（模型供应示范切片）。

组合根（合法装配点，IC-02 例外）：在此处绑定基础设施实现，应用层不感知。
- 结构化路径由 ``repo_bundle_factory`` 提供每请求会话 + 模型仓储束（退出即关会话，连接不泄漏）；
- 供应商按 ``access_protocol`` 经协议注册表解析（真实供应商即插即用，业务不感知）；
- ``port=StubModelAdapter`` 仅作非结构化兜底（生产默认走结构化路径，不触发）。
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from asterism.application.model.use_case import ModelInvokeUseCase
from asterism.infrastructure.model.provider import StubModelAdapter
from asterism.infrastructure.model.provider_registry import resolve_port
from asterism.infrastructure.persistence.db import new_session
from asterism.infrastructure.persistence.engine import get_business_engine
from asterism.infrastructure.persistence.model_repository import (
    SqlVendorRepository,
    SqlPromptTemplateRepository,
)
from asterism.interfaces.model.router import router as model_router


@asynccontextmanager
async def _model_repo_bundle():
    """每请求业务库会话 + 模型仓储束（退出即关会话，连接不泄漏，与厂商管理端点同口径）。"""
    engine = await get_business_engine()
    session = new_session(engine)
    try:
        yield SqlVendorRepository(session), SqlPromptTemplateRepository(session)
    finally:
        await session.close()


def wire_model(app: FastAPI) -> None:
    """装配模型供应应用：注册路由 + 装配用例。"""
    app.include_router(model_router)
    app.state.model_use_case = ModelInvokeUseCase(
        provider_resolver=resolve_port,
        repo_bundle_factory=_model_repo_bundle,
        port=StubModelAdapter(),  # 非结构化兜底（生产默认走结构化路径，不触发）
    )
