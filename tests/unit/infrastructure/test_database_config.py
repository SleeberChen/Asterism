"""数据库配置单元测试（双数据源：系统管理库 admin + 业务库 business）。

验证：默认值按用户规格（nebula/nebula，nebula_admin/nebula_business）；
环境变量覆盖（TC-17）；sqlite 数据源引擎工厂可用。
"""

import pytest

from asterism.infrastructure.persistence.config import DataSourceConfig, DatabaseConfig
from asterism.infrastructure.persistence.db import make_engine_from_datasource


def test_database_config_defaults():
    cfg = DatabaseConfig.load()
    assert cfg.admin.url == "mysql+aiomysql://nebula:nebula@localhost:3306/nebula_admin"
    assert cfg.business.url == "mysql+aiomysql://nebula:nebula@localhost:3306/nebula_business"
    assert cfg.admin.username == "nebula"
    assert cfg.admin.password == "nebula"
    assert cfg.business.username == "nebula"
    assert cfg.business.host == "localhost"
    assert cfg.business.port == 3306


def test_database_config_env_override(monkeypatch):
    monkeypatch.setenv("ASTERISM__DB__ADMIN__URL", "sqlite+aiosqlite:////tmp/asterism_admin.db")
    monkeypatch.setenv("ASTERISM__DB__BUSINESS__URL", "sqlite+aiosqlite:////tmp/asterism_business.db")
    monkeypatch.setenv("ASTERISM__DB__USERNAME", "other")
    monkeypatch.setenv("ASTERISM__DB__PASSWORD", "secret")
    cfg = DatabaseConfig.load()
    assert cfg.admin.url == "sqlite+aiosqlite:////tmp/asterism_admin.db"
    assert cfg.business.url == "sqlite+aiosqlite:////tmp/asterism_business.db"
    # 整串覆盖优先于用户/密码拆分
    assert cfg.admin.username == "other"
    assert cfg.admin.password == "secret"


def test_database_config_builds_mysql_url_from_parts(monkeypatch):
    monkeypatch.setenv("ASTERISM__DB__HOST", "db.example.com")
    monkeypatch.setenv("ASTERISM__DB__PORT", "3307")
    monkeypatch.setenv("ASTERISM__DB__USERNAME", "u")
    monkeypatch.setenv("ASTERISM__DB__PASSWORD", "p")
    cfg = DatabaseConfig.load()
    assert cfg.business.url == "mysql+aiomysql://u:p@db.example.com:3307/nebula_business"


def test_make_engine_from_datasource_sqlite():
    ds = DataSourceConfig("test", "sqlite+aiosqlite:////tmp/asterism_ds_test.db", "u", "p")
    engine = make_engine_from_datasource(ds)
    assert engine.dialect.name == "sqlite"
