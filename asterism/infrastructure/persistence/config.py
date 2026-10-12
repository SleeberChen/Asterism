"""Asterism 数据库配置（配置外部化 TC-17；参照 Nebula 双数据源拓扑）。

Nebula 拓扑：
  - 系统管理库（admin）：租户 / 平台级系统元数据（对应 Nebula nebula_admin）
  - 业务库（business）：业务数据（对应 Nebula nebula_business）
BC-MODEL 等业务聚合根落业务库；租户隔离按字段（tenant_id 列，FIELD 隔离模式）。

默认连接串按用户给出的 JDBC 规格拼出 SQLAlchemy 异步 URL（全链路异步，协程）：
  jdbc:mysql://localhost:3306/nebula_admin
    → mysql+aiomysql://nebula:nebula@localhost:3306/nebula_admin

凭据 / 连接串经环境变量覆盖（生产严禁明文，须走密钥 / 配置中心）：
  ASTERISM__DB__HOST / ASTERISM__DB__PORT
  ASTERISM__DB__USERNAME / ASTERISM__DB__PASSWORD
  ASTERISM__DB__ADMIN__URL / ASTERISM__DB__BUSINESS__URL（整串覆盖优先）
注：全链路异步，默认驱动 mysql+aiomysql://（需 pip install aiomysql）；sqlite 测试用 sqlite+aiosqlite://。
"""

from __future__ import annotations

import os
from dataclasses import dataclass

# --- 默认值（本地开发 / 草稿口径；生产由环境变量覆盖）---
DEFAULT_HOST: str = "localhost"
DEFAULT_PORT: int = 3306
DEFAULT_USERNAME: str = "nebula"
DEFAULT_PASSWORD: str = "nebula"
ADMIN_DB: str = "nebula_admin"
BUSINESS_DB: str = "nebula_business"
ENV_PREFIX: str = "ASTERISM"


def _env(key: str, default: str) -> str:
    v = os.environ.get(key)
    return v if v not in (None, "") else default


def _build_mysql_url(host: str, port: int, db: str, username: str, password: str) -> str:
    # 全链路异步：默认驱动 mysql+aiomysql://（SQLAlchemy 异步引擎）
    return f"mysql+aiomysql://{username}:{password}@{host}:{port}/{db}"


@dataclass(frozen=True)
class DataSourceConfig:
    """单一数据源配置（名称 + SQLAlchemy URL + 凭据 + 连接信息）。"""

    name: str
    url: str
    username: str
    password: str
    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT

    @property
    def engine_kwargs(self) -> dict:
        # SQLite 关掉单线程限制以支持多会话共享；MySQL 可加 pool_pre_ping 等
        if self.url.startswith("sqlite"):
            return {"connect_args": {"check_same_thread": False}}
        return {}


@dataclass(frozen=True)
class DatabaseConfig:
    """框架级数据库配置：admin（系统管理库）+ business（业务库）双数据源。"""

    admin: DataSourceConfig
    business: DataSourceConfig

    @classmethod
    def load(cls, prefix: str = ENV_PREFIX) -> "DatabaseConfig":
        host = _env(f"{prefix}__DB__HOST", DEFAULT_HOST)
        port = int(_env(f"{prefix}__DB__PORT", str(DEFAULT_PORT)))
        username = _env(f"{prefix}__DB__USERNAME", DEFAULT_USERNAME)
        password = _env(f"{prefix}__DB__PASSWORD", DEFAULT_PASSWORD)

        admin_url = _env(
            f"{prefix}__DB__ADMIN__URL",
            _build_mysql_url(host, port, ADMIN_DB, username, password),
        )
        business_url = _env(
            f"{prefix}__DB__BUSINESS__URL",
            _build_mysql_url(host, port, BUSINESS_DB, username, password),
        )
        return cls(
            admin=DataSourceConfig("admin", admin_url, username, password, host, port),
            business=DataSourceConfig("business", business_url, username, password, host, port),
        )
