"""分层依赖守护（GATE-04）。

与 ``architecture_layering.toml``（P5 §2.2 依赖矩阵同源）一致：扫描 ``asterism/**/*.py``
的 import 图，断言无反向 / 越层依赖（TC-09 分层单向、TC-10 领域零框架、TC-11 插件内核不反向依赖）。

退出码：发现违规 = 1；无违规 = 0（门禁不得消音，TC-22）。
用法：
    python tools/check_layering.py                 # 扫描 asterism/ 包
    python tools/check_layering.py --self-test     # 注入 5 个反向样本，验证 100% 拦截
"""

from __future__ import annotations

import argparse
import ast
import sys
import tempfile
import tomllib
from pathlib import Path
from typing import Dict, List, Tuple

TOOL_DIR = Path(__file__).resolve().parent
ROOT = TOOL_DIR.parent  # asterism-code/
CONTRACT = TOOL_DIR / "architecture_layering.toml"

# 文件所属区域（按路径片段分类）；组合根 asterism/main.py 为 root（允许全部）
_PATH_AREA_RULES = [
    ("/seedwork/", "seedwork"),
    ("/interfaces/", "interfaces"),
    ("/application/", "application"),
    ("/domain/", "domain"),
    ("/infrastructure/", "infrastructure"),
    ("/plugins/kernel/", "plugins_kernel"),
    ("/plugins/model/", "plugins_model"),
    ("/plugins/tool/", "plugins_tool"),
    ("/plugins/skill/", "plugins_skill"),
    ("/plugins/memory/", "plugins_memory"),
]


def load_contract() -> Tuple[Dict[str, str], Dict[str, List[str]]]:
    with CONTRACT.open("rb") as fh:
        data = tomllib.load(fh)
    areas: Dict[str, str] = data["areas"]
    allowed: Dict[str, List[str]] = data["allowed"]
    return areas, allowed


def area_of_path(path: Path, root: Path) -> str:
    rel = str(path.relative_to(root)).replace("\\", "/")
    for frag, area in _PATH_AREA_RULES:
        if frag in rel:
            return area
    return "root"  # asterism/main.py / asterism/__init__.py


def area_of_module(module: str, areas: Dict[str, str]) -> str | None:
    if not module.startswith("asterism"):
        return None  # 非 asterism 依赖（fastapi/pydantic 等），忽略
    for area, prefix in areas.items():
        if module == prefix or module.startswith(prefix + "."):
            return area
    return "root"  # 未知 asterism 子模块，按 root 处理（allowed 不限制）


def collect_imports(path: Path) -> List[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    mods: List[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                mods.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:
                mods.append(node.module)
    return mods


def check_dir(pkg_dir: Path, areas: Dict[str, str], allowed: Dict[str, List[str]]) -> List[str]:
    root = pkg_dir.parent  # 区域判定相对包父目录（支持临时样本根）
    violations: List[str] = []
    for py in sorted(pkg_dir.rglob("*.py")):
        src_area = area_of_path(py, root)
        if src_area == "root":
            continue  # 组合根允许依赖全部区域
        for mod in collect_imports(py):
            tgt_area = area_of_module(mod, areas)
            if tgt_area is None or tgt_area == "root":
                continue
            permitted = allowed.get(src_area, [])
            if tgt_area not in permitted:
                violations.append(
                    f"{py.relative_to(root)} : 禁止 {src_area} → {tgt_area} "
                    f"(import {mod})"
                )
    return violations


def self_test(areas: Dict[str, str], allowed: Dict[str, List[str]]) -> int:
    """注入 5 个反向依赖样本，验证全部被拦截（拦截率 = 100%）。"""
    samples = [
        ("domain/rag/x.py", "from asterism.interfaces.rag.router import router\n"),
        ("application/rag/x.py", "from asterism.interfaces.rag.router import router\n"),
        ("plugins/kernel/x.py", "from asterism.plugins.model.stub import StubModelProvider\n"),
        ("plugins/model/x.py", "from asterism.plugins.tool.base import ToolProvider\n"),
        ("infrastructure/rag/x.py", "from asterism.application.rag.use_case import RagQueryUseCase\n"),
    ]
    with tempfile.TemporaryDirectory() as td:
        pkg = Path(td) / "asterism"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("")
        for rel, content in samples:
            f = pkg / rel
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(content)
        found = check_dir(pkg, areas, allowed)
    # 5 个样本均须被检测到
    ok = len(found) == len(samples)
    print(f"[self-test] 注入样本 {len(samples)} 个，检出违规 {len(found)} 个 -> "
          f"{'PASS（拦截率100%）' if ok else 'FAIL'}")
    for v in found:
        print("  -", v)
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="Asterism 分层依赖守护（GATE-04）")
    ap.add_argument("--self-test", action="store_true", help="注入反向样本验证 100% 拦截")
    ap.add_argument("--pkg", type=Path, default=ROOT / "asterism",
                    help="待扫描的 asterism 包目录")
    args = ap.parse_args()

    areas, allowed = load_contract()

    if args.self_test:
        return self_test(areas, allowed)

    pkg = args.pkg
    if not pkg.exists():
        print(f"包目录不存在：{pkg}", file=sys.stderr)
        return 2

    violations = check_dir(pkg, areas, allowed)
    if violations:
        print(f"发现 {len(violations)} 条分层依赖违规：")
        for v in violations:
            print("  -", v)
        print("GATE-04: FAIL（拦截率须 = 100%，AST-ARCH-R-001）")
        return 1
    print("GATE-04: PASS（无反向 / 越层依赖）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
