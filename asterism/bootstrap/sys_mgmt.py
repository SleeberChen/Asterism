"""APP-SYSMGMT 装配（仅独立部署形态启用，P3 §7.1 / P0 CON05）。"""

from __future__ import annotations

import os

from fastapi import FastAPI

from asterism.application.sys_mgmt.use_case import ListDirectoryUseCase
from asterism.infrastructure.config.settings import load_settings
from asterism.infrastructure.sys_mgmt.directory import InMemoryUserDirectory
from asterism.interfaces.sys_mgmt.router import router as sys_mgmt_router
from asterism.seedwork.logging import get_logger

logger = get_logger(__name__)

# 独立部署（默认可运行，12/12 应用）；并入星云（11/12，APP-SYSMGMT 不启用）
STANDALONE = "standalone"


def _deployment_mode() -> str:
    """读取运行形态（外部化配置 + 环境变量覆盖，TC-17）。

    可用 ``ASTERISM__DEPLOYMENT__MODE=nebula`` 覆盖；环境名用 ``ASTERISM_ENV``。
    """
    env_name = os.environ.get("ASTERISM_ENV", "base")
    return str(load_settings(env_name).get("deployment.mode", STANDALONE)).lower()


def wire_sys_mgmt(app: FastAPI) -> None:
    """装配系统管理应用；并入星云形态下跳过（用户 / 权限由星云提供）。"""
    mode = _deployment_mode()
    if mode != STANDALONE:
        logger.info("APP-SYSMGMT 未装配（并入星云形态）", extra={"deployment_mode": mode})
        return

    app.include_router(sys_mgmt_router)
    app.state.sys_mgmt_directory_use_case = ListDirectoryUseCase(
        directory=InMemoryUserDirectory()
    )
