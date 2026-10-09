"""APP-MODEL 装配（模型供应示范切片）。"""

from __future__ import annotations

from fastapi import FastAPI

from asterism.application.model.use_case import ModelInvokeUseCase
from asterism.infrastructure.model.provider import StubModelAdapter
from asterism.interfaces.model.router import router as model_router


def wire_model(app: FastAPI) -> None:
    """装配模型供应应用：注册路由 + 装配用例（经插件内核注册的桩适配器）。"""
    app.include_router(model_router)
    app.state.model_use_case = ModelInvokeUseCase(port=StubModelAdapter())
