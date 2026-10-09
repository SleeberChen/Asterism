"""Asterism 应用入口（组合根 + ASGI 工厂 + 全局异常）。

组合根（Composition Root）：在应用层 / 接口层之外装配依赖，是依赖倒置的合法装配点
（P5 TC-09：依赖方向违规只发生在业务模块，组合根例外）。

本文件保持**薄**：不感知任何具体应用。逐应用的路由注册与用例装配下沉到
``asterism/bootstrap/``（新增应用＝新增 ``bootstrap/<app>.py`` + 登记进
``registry.APP_WIRINGS``，本文件不改）。原因与纪律见 ``bootstrap/__init__.py``。

运行形态双模（P0 CON05）：同一份代码，独立部署自带 APP-SYSMGMT，并入星云复用星云权限；
差异仅出现在兼容点（CP-*），本骨架以配置开关区分。
"""

from __future__ import annotations

from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from asterism.bootstrap import register_apps
from asterism.plugins.kernel.registry import get_registry
from asterism.plugins.model.stub import StubModelProvider
from asterism.seedwork.exceptions import AsterismError
from asterism.seedwork.logging import get_logger

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动：注册插件、启动生命周期（多 worker 下注意只执行一次，P5 ASGI 章节）
    registry = get_registry()
    registry.register(StubModelProvider())  # 经内核注册模型插件（TC-11）
    registry.start_all()
    logger.info("Asterism 应用启动完成")
    yield
    registry.stop_all()
    logger.info("Asterism 应用关闭")


def create_app() -> FastAPI:
    """FastAPI 应用工厂。"""
    app = FastAPI(
        title="Asterism",
        version="0.1.0",
        debug=False,  # 生产默认关闭调试，避免泄露内部细节（TC-16）
        lifespan=lifespan,
    )

    # 应用装配：按 bootstrap/registry.py 的注册表逐应用注册（新增应用不改此处）
    register_apps(app)

    @app.exception_handler(AsterismError)
    async def _handle_asterism(_: Request, exc: AsterismError) -> JSONResponse:
        # 对外只暴露 AST-ERR 错误码 + 用户可读信息 + 链路标识（TC-16）
        return JSONResponse(status_code=exc.http_status, content=exc.to_dict())

    @app.exception_handler(Exception)
    async def _handle_unexpected(_: Request, exc: Exception) -> JSONResponse:
        # 兜底：未预期异常统一为内部错误，不泄露堆栈 / SQL / 内网地址（TC-16）
        logger.error("未预期异常", extra={"exc": type(exc).__name__})
        return JSONResponse(
            status_code=500,
            content={"code": "AST-ERR-5001", "message": "内部未预期错误", "request_id": None},
        )

    @app.get("/healthz", tags=["health"])
    async def health() -> dict:
        return {"status": "ok"}

    return app


app = create_app()


if __name__ == "__main__":
    uvicorn.run("asterism.main:app", host="0.0.0.0", port=8000, reload=False)
