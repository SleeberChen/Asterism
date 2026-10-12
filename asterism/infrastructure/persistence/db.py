"""BC-MODEL 持久化基座（SQLAlchemy 2.x 异步 + SQLite/MySQL 默认；生产可换 PostgreSQL）。

DB 实现替换原内存仓储，仓储接口（方法签名）保持不变（DMP-13 聚合=事务边界，本地强一致）。
凭据句柄（L3）仅存密文定位引用，绝不落明文（承接 P4 L3 口径）。

版本控制（参照 Nebula Flyway 风格，取代 Base.metadata.create_all 自动 DDL）：
  建表由版本化迁移 SQL 驱动，而非 ORM 自动建表：
  - 迁移脚本落点：<repo>/db/migration/<dialect>/V<major>.<minor>.<patch>__<desc>.sql
  - 已应用版本记录于 schema_version 表（轻量 flyway_schema_history）
  - init_db(engine) 调用 apply_migrations 幂等重放未应用脚本（按版本升序、同事务落 DDL + 记版本）

全链路异步：引擎为 AsyncEngine，会话为 AsyncSession，迁移与建表均为协程（需 running loop）。
"""

from __future__ import annotations

import datetime
import hashlib
import os
import re
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base

from .config import DataSourceConfig, DatabaseConfig

Base = declarative_base()

_MIGRATION_VERSION_RE = re.compile(r"^V(\d+)\.(\d+)\.(\d+)__(.+)\.sql$")


def _default_url() -> str:
    # 统一默认数据库为 MySQL（异步驱动 aiomysql；业务库）；可用 ASTERISM__DATABASE__URL 覆盖
    env = os.environ.get("ASTERISM__DATABASE__URL")
    if env:
        return env
    return DatabaseConfig.load().business.url


def _default_migration_dir() -> Path:
    # 从本文件向上查找含 db/migration 的仓库根（对目录层级变化稳健）
    here = Path(__file__).resolve().parent
    for cand in [here, *here.parents]:
        d = cand / "db" / "migration"
        if d.is_dir():
            return d
    # 兜底：约定路径（persistence 上溯至仓库根）
    return here.parent.parent.parent / "db" / "migration"


def make_engine(url: str | None = None) -> AsyncEngine:
    """创建异步引擎；SQLite 关掉单线程限制以支持多会话共享。"""
    if url is None:
        url = _default_url()
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    return create_async_engine(url, connect_args=connect_args, future=True)


def make_engine_from_datasource(ds: DataSourceConfig) -> AsyncEngine:
    """由数据源配置创建异步引擎（URL + 方言相关 connect_args）。"""
    return create_async_engine(ds.url, **ds.engine_kwargs, future=True)


def make_admin_engine(config: DatabaseConfig | None = None) -> AsyncEngine:
    """系统管理库引擎（nebula_admin）。"""
    cfg = config or DatabaseConfig.load()
    return make_engine_from_datasource(cfg.admin)


def make_business_engine(config: DatabaseConfig | None = None) -> AsyncEngine:
    """业务库引擎（nebula_business）；BC-MODEL 等业务聚合根落此库。"""
    cfg = config or DatabaseConfig.load()
    return make_engine_from_datasource(cfg.business)


async def init_business_db(config: DatabaseConfig | None = None) -> AsyncEngine:
    """初始化业务库（建表 + 版本记录），返回已初始化的业务异步引擎。"""
    engine = make_business_engine(config)
    await apply_migrations(engine)
    return engine


def _dialect_name(engine: AsyncEngine) -> str:
    name = engine.dialect.name
    if name.startswith("postgre"):
        return "postgresql"
    if name.startswith("mysql"):
        return "mysql"
    if name.startswith("sqlite"):
        return "sqlite"
    return name


def _discover_migrations(migrations_dir: Path, dialect: str) -> list[Path]:
    d = migrations_dir / dialect
    if d.is_dir():
        return sorted(d.glob("V*__*.sql"))
    return sorted(migrations_dir.glob("V*__*.sql"))


def _split_sql(sql: str) -> list[str]:
    """按语句分割（迁移脚本内无字符串内分号，安全）。"""
    return [s.strip() for s in sql.split(";") if s.strip()]


async def _ensure_schema_version(engine: AsyncEngine) -> None:
    # 版本历史表本身由运行器创建（基础设施，不计入领域迁移）。
    # 列用 VARCHAR 而非 TEXT：MySQL 不允许 TEXT 作主键
    # （"BLOB/TEXT column used in key specification without a key length"）；
    # VARCHAR 在 sqlite / mysql / postgresql 下均兼容。
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS schema_version ("
                "  version VARCHAR(50) NOT NULL,"
                "  description VARCHAR(200) NOT NULL,"
                "  script VARCHAR(200) NOT NULL,"
                "  checksum VARCHAR(64),"
                "  installed_by VARCHAR(100),"
                "  installed_on VARCHAR(40) NOT NULL,"
                "  execution_time INTEGER,"
                "  success INTEGER NOT NULL,"
                "  PRIMARY KEY (version)"
                ")"
            )
        )


async def _applied_versions(engine: AsyncEngine) -> set[str]:
    async with engine.connect() as conn:
        res = await conn.execute(text("SELECT version FROM schema_version WHERE success = 1"))
        return {r[0] for r in res.fetchall()}


def _version_key(path: Path) -> tuple[int, int, int]:
    m = _MIGRATION_VERSION_RE.match(path.name)
    if not m:
        return (0, 0, 0)
    return (int(m.group(1)), int(m.group(2)), int(m.group(3)))


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


async def apply_migrations(engine: AsyncEngine, migrations_dir: Path | None = None) -> list[str]:
    """幂等重放未应用的版本化迁移脚本，返回本次应用的脚本名列表。

    语义（参照 Flyway）：
      - 同一事务内执行 DDL 并登记 schema_version（含 checksum / installed_on / success）
      - 已 success=1 的版本跳过；失败落 success=0 并重抛，下次重放因 IF NOT EXISTS 幂等
    """
    migrations_dir = migrations_dir or _default_migration_dir()
    dialect = _dialect_name(engine)
    await _ensure_schema_version(engine)
    applied = await _applied_versions(engine)

    applied_now: list[str] = []
    for path in _discover_migrations(migrations_dir, dialect):
        ver = ".".join(str(x) for x in _version_key(path))
        if ver in applied:
            continue
        m = _MIGRATION_VERSION_RE.match(path.name)
        desc = m.group(4) if m else path.stem
        sql = path.read_text(encoding="utf-8")
        checksum = hashlib.sha256(sql.encode("utf-8")).hexdigest()
        try:
            async with engine.begin() as conn:
                for stmt in _split_sql(sql):
                    await conn.execute(text(stmt))
                await conn.execute(
                    text(
                        "INSERT INTO schema_version "
                        "(version, description, script, checksum, installed_on, success) "
                        "VALUES (:v, :d, :s, :c, :t, 1)"
                    ),
                    {"v": ver, "d": desc, "s": path.name, "c": checksum, "t": _now_iso()},
                )
        except Exception:
            # 记录失败并重抛；下次重放因 IF NOT EXISTS 幂等
            try:
                async with engine.begin() as conn:
                    await conn.execute(
                        text(
                            "INSERT INTO schema_version "
                            "(version, description, script, checksum, installed_on, success) "
                            "VALUES (:v, :d, :s, :c, :t, 0)"
                        ),
                        {"v": ver, "d": desc, "s": path.name, "c": checksum, "t": _now_iso()},
                    )
            except Exception:
                pass
            raise
        applied.add(ver)
        applied_now.append(path.name)
    return applied_now


async def init_db(engine: AsyncEngine) -> None:
    """建表（版本化迁移，幂等）。参照 Nebula Flyway 风格，取代自动 DDL。"""
    await apply_migrations(engine)


def new_session(engine: AsyncEngine) -> AsyncSession:
    return AsyncSession(engine, expire_on_commit=False)
