"""错误码与统一错误响应契约（P5 §14.4.3）。

错误码格式：``AST-ERR-{4 位序号}``（4 位是为避免与编号门禁正则「末段 1~3 位数字」撞名）。
分段：1xxx 通用 / 2xxx 认证授权 / 3xxx 参数校验 / 4xxx 外部依赖 / 5xxx 内部错误。
错误码属运行时编码，不进 ``10-spec/编号登记册.md``。
新增错误码须登记（平台架构组批准）并在本表补行；未登记错误码数 = 0。
"""

from __future__ import annotations

from typing import Dict, Tuple

# (code) -> (用户可读信息, HTTP 状态码)
# 初始条目承接 P5 §14.4.3；P8 补齐枚举时同步扩展。
_ERROR_REGISTRY: Dict[str, Tuple[str, int]] = {
    "AST-ERR-2001": ("未认证 / 认证失败", 401),
    "AST-ERR-2002": ("越权（功能权限不足）", 403),
    "AST-ERR-2003": ("越权（数据权限 / 跨租户 / 跨平面）", 403),
    "AST-ERR-2004": ("隔离上下文缺失（拒绝服务，不兜底）", 400),
    "AST-ERR-3001": ("参数校验失败", 400),
    "AST-ERR-3002": ("会话上下文超限（已截断并显式提示）", 400),
    "AST-ERR-4001": ("模型供应商不可用且回退失败", 502),
    "AST-ERR-4002": ("外部依赖超时", 504),
    "AST-ERR-5001": ("内部未预期错误", 500),
}

# 错误码正则（校验新增错误码格式；用于自测与未来登记校验）
import re  # noqa: E402  # 置于 registry 之后，保持表可读

_ERR_CODE_RE = re.compile(r"^AST-ERR-\d{4}$")


def is_registered(code: str) -> bool:
    """错误码是否已登记。"""
    return code in _ERROR_REGISTRY


def message_for(code: str) -> str:
    """返回错误码的用户可读信息；未登记时返回通用内部错误文案（不泄露未知码含义）。"""
    if code in _ERROR_REGISTRY:
        return _ERROR_REGISTRY[code][0]
    return _ERROR_REGISTRY["AST-ERR-5001"][0]


def http_status_for(code: str) -> int:
    """返回错误码对应的 HTTP 状态码；未登记默认 500。"""
    return _ERROR_REGISTRY.get(code, (None, 500))[1]


def register(code: str, message: str, http_status: int) -> None:
    """登记新错误码（平台架构组批准后方可调用）。

    约束：code 必须符合 ``AST-ERR-{4位}``；未登记错误码数须 = 0。
    """
    if not _ERR_CODE_RE.match(code):
        raise ValueError(f"错误码格式非法：{code!r}，应为 AST-ERR-####")
    _ERROR_REGISTRY[code] = (message, http_status)
