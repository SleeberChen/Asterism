"""Asterism 应用入口（组合根 + ASGI 工厂 + 全局异常）。

组合根（Composition Root）：在应用层 / 接口层之外装配依赖，是依赖倒置的合法装配点
（P5 TC-09：依赖方向违规只发生在业务模块，组合根例外）。

本文件保持**薄**：不感知任何具体应用。逐应用的路由注册与用例装配下沉到
``asterism/bootstrap/``（新增应用＝新增 ``bootstrap/<app>.py`` + 登记进
``registry.APP_WIRINGS``，本文件不改）。原因与纪律见 ``bootstrap/__init__.py``。

运行形态双模（P0 CON05）：同一份代码，独立部署自带 APP-SYSTEM，并入星云复用星云权限；
差异仅出现在兼容点（CP-*），本骨架以配置开关区分。

统一响应规范（强制，见 ``asterism/interfaces/common/result.py``）：
- 成功响应由路由返回 ``ApiResult[<业务 Schema>]``。
- 所有失败（``AsterismError`` / 参数校验 / 未预期异常）在本文件统一映射为
  ``ApiResult.fail(...)`` 信封；路由内不得手写 ``JSONResponse(exc.to_dict())``。
- ``/healthz`` 探针与 204 No Content 按设计豁免包裹。
"""

from __future__ import annotations

from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from asterism.bootstrap import register_apps
from asterism.interfaces.common.result import ApiResult
from asterism.plugins.kernel.registry import get_registry
from asterism.plugins.model.stub import StubModelProvider
from asterism.seedwork.exceptions import AsterismError
from asterism.seedwork.logging import get_logger

logger = get_logger(__name__)


def install_exception_handlers(app: FastAPI) -> None:
    """注册全局异常处理器：所有失败统一映射为 ``ApiResult.fail(...)`` 信封（强制规范）。

    集中登记点，供 ``create_app`` 与需复用鉴权依赖的契约测试共享，避免逻辑漂移。
    """

    @app.exception_handler(AsterismError)
    async def _handle_asterism(_: Request, exc: AsterismError) -> JSONResponse:
        # 对外只暴露 AST-ERR 错误码 + 用户可读信息 + 链路标识（TC-16）
        return JSONResponse(
            status_code=exc.http_status,
            content=ApiResult.fail(
                code=exc.code,
                message=exc.message,
                request_id=exc.request_id,
            ).model_dump(),
        )

    @app.exception_handler(RequestValidationError)
    async def _handle_validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        # FastAPI 参数校验失败（422）统一映射为 AST-ERR-3001 信封
        return JSONResponse(
            status_code=422,
            content=ApiResult.fail(
                code="AST-ERR-3001",
                message="参数校验失败",
                data=exc.errors(),
            ).model_dump(),
        )

    @app.exception_handler(Exception)
    async def _handle_unexpected(_: Request, exc: Exception) -> JSONResponse:
        # 兜底：未预期异常统一为内部错误，不泄露堆栈 / SQL / 内网地址（TC-16）
        logger.error("未预期异常", extra={"exc": type(exc).__name__})
        return JSONResponse(
            status_code=500,
            content=ApiResult.fail(code="AST-ERR-5001", message="内部未预期错误").model_dump(),
        )


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

    # 全局异常统一映射为响应信封（强制规范，集中登记）
    install_exception_handlers(app)

    @app.get("/healthz", tags=["health"])
    async def health() -> dict:
        # 探针豁免包裹（无统一信封，属设计豁免）
        return {"status": "ok"}

    return app


app = create_app()


if __name__ == "__main__":
    uvicorn.run("asterism.main:app", host="0.0.0.0", port=8000, reload=False)
