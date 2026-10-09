"""配置加载（P5 TC-17 外部化 / M6 分层加载 / TC-02 密钥只写不读）。

- 配置外部化：供应商清单、租户策略、中间件地址、端点等不得硬编码（TC-17）。
- 分层加载（M6）：base.yaml + 环境覆盖层（dev/test/prod）+ 环境变量覆盖。
- 密钥只写不读（TC-02）：密钥类配置项仅以 ``SecretRef`` 持有「定位引用」（环境变量名 /
  KMS key id），运行时只传递定位引用给供应商，不把明文读回内存 / 日志。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

from asterism.seedwork.logging import get_logger

logger = get_logger(__name__)

_CONFIG_DIR = Path(__file__).resolve().parents[3] / "configs"
_SECRET_HINT_KEYS = ("secret", "api_key", "apikey", "token", "password", "credential", "private_key")


@dataclass(frozen=True)
class SecretRef:
    """密钥定位引用（TC-02：只写不可读）。

    仅持有定位符（如环境变量名），不含明文。运行时把该引用交给密钥后端 / 供应商，
    应用代码不读取明文，可读次数 = 0。
    """

    locator: str  # 例如环境变量名 "MODEL_API_KEY" 或 KMS key id

    def __repr__(self) -> str:  # 禁止泄露定位之外的信息
        return f"SecretRef(locator={self.locator!r})"


def _is_secret_key(key: str) -> bool:
    k = key.lower().replace("-", "_").replace(".", "_")
    return any(p in k for p in _SECRET_HINT_KEYS)


class Settings:
    """分层配置容器。

    非密钥配置以普通值暴露；密钥配置以 ``SecretRef`` 暴露（不可读明文）。
    """

    def __init__(self, data: Dict[str, Any]) -> None:
        self._data = data

    def get(self, path: str, default: Optional[Any] = None) -> Any:
        """按点路径读取非密钥配置，如 ``model.providers[0].name``。"""
        node: Any = self._data
        for part in path.split("."):
            if isinstance(node, dict) and part in node:
                node = node[part]
            else:
                return default
        # 若命中密钥键，返回定位引用而非明文
        if isinstance(node, str) and _is_secret_key(path.split(".")[-1]):
            return SecretRef(locator=node)
        return node

    def get_secret_ref(self, path: str) -> Optional[SecretRef]:
        """读取密钥定位引用（仅返回定位符，不返回明文，TC-02）。"""
        val = self.get(path)
        if isinstance(val, SecretRef):
            return val
        return None

    def as_dict(self) -> Dict[str, Any]:
        """导出非密钥配置（密钥一律脱敏为定位引用，绝不输出明文，TC-14/L3）。"""

        def walk(node: Any) -> Any:
            if isinstance(node, dict):
                return {k: (SecretRef(locator=v) if _is_secret_key(k) else walk(v)) for k, v in node.items()}
            if isinstance(node, list):
                return [walk(v) for v in node]
            return node

        return walk(self._data)


def _overlay_env(data: Dict[str, Any]) -> Dict[str, Any]:
    """环境变量覆盖：``ASTERISM__<SECTION>__<KEY>`` 形式覆盖末级值（仅非密钥）。"""
    prefix = "ASTERISM__"
    for env_key, env_val in os.environ.items():
        if not env_key.startswith(prefix):
            continue
        parts = env_key[len(prefix):].lower().split("__")
        node = data
        for p in parts[:-1]:
            node = node.setdefault(p, {})
        node[parts[-1]] = env_val
    return data


def load_settings(env_name: str = "base") -> Settings:
    """加载 base + 环境覆盖层 + 环境变量。

    :param env_name: 环境名（base/dev/test/prod），对应 ``configs/<env>.yaml``。
    """
    merged: Dict[str, Any] = {}
    for name in ("base", env_name):
        if name == "base" and env_name == "base":
            path = _CONFIG_DIR / "base.yaml"
        else:
            path = _CONFIG_DIR / f"{name}.yaml"
        if path.exists():
            with path.open("r", encoding="utf-8") as fh:
                loaded = yaml.safe_load(fh) or {}
            _deep_merge(merged, loaded)
    _overlay_env(merged)
    # 不记录含密钥的配置（TC-14：密钥不得入日志）
    logger.info("配置已加载", extra={"env": env_name})
    return Settings(merged)


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> None:
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v
