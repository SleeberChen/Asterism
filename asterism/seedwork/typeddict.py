"""TypedDict 运行时形状校验（领域模型守卫）。

背景：`TypedDict` 只提供**静态**类型信息，运行时它就是普通 ``dict``，不做任何校验。
为使「domain 使用 TypedDict 进行校验」在**运行时**同样成立，本模块提供轻量校验器：
必填键缺失 / 顶层类型不符即抛 ``AST-ERR-3001``（不吞、不兜底，TC-15/16）。

设计取舍：
- 只做**顶层**类型校验（不递归嵌套、不校验容器元素），保持零依赖与可预测开销；
- 嵌套 `TypedDict` 仅判定为 ``dict``（避免 ``isinstance`` 对 TypedDict 抛 TypeError）；
- 复杂业务不变量仍由领域服务显式校验，不靠本模块。
"""

from __future__ import annotations

import types
from typing import (
    Any,
    List,
    Optional,
    Type,
    get_args,
    get_origin,
    get_type_hints,
    is_typeddict,
)

from .exceptions import BusinessError


def _candidates(hint: Any) -> tuple:
    """展开 ``Optional[X]`` / ``Union[...]`` / 泛型为候选顶层类型元组。"""
    origin = get_origin(hint)
    if origin is types.UnionType or str(origin) == "typing.Union":
        return get_args(hint)
    if origin is not None:
        return (origin,)  # List[...] -> list；Dict[...] -> dict
    return (hint,)


def _matches(value: Any, cand: Any) -> bool:
    """顶层类型判定（容器只判容器类型，不递归元素）。"""
    if cand is Any:
        return True
    if cand is type(None):
        return value is None
    if is_typeddict(cand):
        return isinstance(value, dict)  # 嵌套 TypedDict 只判定为 dict
    try:
        return isinstance(value, cand)
    except TypeError:
        return True  # 无法判定的类型不误报


def validate_typed_dict(value: Any, td: Type, *, name: Optional[str] = None) -> None:
    """校验 ``value`` 是否符合 ``td``（TypedDict）形状；不符抛 ``AST-ERR-3001``。

    :raises BusinessError: 非 dict / 缺必填键 / 顶层类型不符。
    """
    if not is_typeddict(td):
        raise BusinessError("AST-ERR-3001", message=f"{name or td!r} 不是 TypedDict 类型")

    label = name or getattr(td, "__name__", str(td))
    if not isinstance(value, dict):
        raise BusinessError(
            "AST-ERR-3001", message=f"{label} 须为 dict，实际为 {type(value).__name__}"
        )

    required = set(getattr(td, "__required_keys__", ()) or ())
    missing = sorted(k for k in required if k not in value)
    if missing:
        raise BusinessError(
            "AST-ERR-3001", message=f"{label} 缺少必填字段：{', '.join(missing)}"
        )

    hints = get_type_hints(td)
    bad: List[str] = []
    for key, val in value.items():
        if key not in hints:
            continue  # TypedDict 运行时允许额外键，不校验
        if val is None:
            continue  # 由 Optional 显式声明的字段允许 None
        if not any(_matches(val, cand) for cand in _candidates(hints[key])):
            bad.append(f"{key} 期望 {hints[key]}，实际 {type(val).__name__}")
    if bad:
        raise BusinessError("AST-ERR-3001", message=f"{label} 字段类型不符：{'; '.join(bad)}")
