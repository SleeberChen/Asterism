"""契约测试 `T-CONTRACT-10` → `IC-10` 租户 / 权限语义契约（星云对齐）。

测试意图（P3 02-应用间契约.md）：
- 权限语义要素逐项有结论（未比对 = 0）；
- **本期与星云运行时打通功能交付数 = 0**（`AC-TENANT-11`：只对齐不打通）。

本期只做**语义对齐**（三层可见上限 `L0 ⊇ L1 ⊇ L2`、管控面 / 业务数据面双平面、
break-glass 五要素），不交付运行时打通能力，故以「无集成交付」为可判定断言。
"""
from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_default_deployment_mode_is_standalone():
    """本期默认形态＝独立部署（自带系统管理模块最小集），非并入星云运行时。"""
    cfg = yaml.safe_load((REPO_ROOT / "configs" / "base.yaml").read_text(encoding="utf-8"))
    assert cfg["deployment"]["mode"] == "standalone"


def test_no_nebula_runtime_integration_is_delivered():
    """运行时打通功能交付数 = 0：依赖清单与源码均不引入星云运行时 SDK。"""
    pyproject = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8").lower()
    forbidden_sdk = ("nacos", "nebula-sdk", "nebula-client", "asterism-nebula")
    hits = [name for name in forbidden_sdk if name in pyproject]
    assert hits == [], f"出现星云运行时集成依赖（本期应为 0 交付）：{hits}"

    offenders: list[str] = []
    for path in (REPO_ROOT / "asterism").rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        text = path.read_text(encoding="utf-8").lower()
        if any(name in text for name in forbidden_sdk):
            offenders.append(str(path.relative_to(REPO_ROOT)))
    assert offenders == [], f"源码出现星云运行时集成（本期应为 0 交付）：{offenders}"
