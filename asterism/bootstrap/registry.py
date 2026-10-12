"""应用装配注册表。

新增应用只需：① 新增 `bootstrap/<app>.py` 暴露 `wire_<app>(app)`；
② 在本文件 `APP_WIRINGS` 追加一行。`main.py` 无需改动（开闭原则）。
"""

from __future__ import annotations

from typing import Callable, List

from fastapi import FastAPI

from .compliance import wire_compliance
from .model import wire_model
from .rag import wire_rag
from .system import wire_system

# 装配顺序＝注册顺序。COMPLIANCE 为横切基座（其余应用复用其鉴权），须置于依赖鉴权者之前；
# SYSTEM 仅独立部署形态装配（并入星云自动跳过），置于末尾。
APP_WIRINGS: List[Callable[[FastAPI], None]] = [
    wire_compliance,  # 安全合规骨架（横切基座：鉴权判定 / 审计留痕 / break-glass）
    wire_rag,         # 示范业务应用（内部知识库问答）
    wire_model,       # APP-MODEL 示范切片
    wire_system,      # APP-SYSTEM（仅独立部署形态装配）
]


def register_apps(app: FastAPI) -> None:
    """按注册表逐应用装配：注册路由 + 装配该应用的用例到 ``app.state``。"""
    for wire in APP_WIRINGS:
        wire(app)
