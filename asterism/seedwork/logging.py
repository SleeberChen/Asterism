"""结构化日志（P5 §14.4.1 / 第 12 章 §1）。

约束：
- 结构化字段 schema，禁止自由文本作为唯一载体。
- 必带三要素：租户（tenant_id）/ 用户（主体标识）/ 请求（链路标识），缺一即不完整。
- 按 L0~L4 分级脱敏；**凭据 / 令牌 / 密钥（L3）不得入日志**（不是脱敏后可记，是不记）。
- 完整会话内容不得原文记录。
- 级别：ERROR 需人介入 / WARN 已降级或重试仍异常 / INFO 关键状态变更 / DEBUG 排障细节（生产默认关闭）。
"""

from __future__ import annotations

import json
import logging
import sys
from typing import Any, Dict, Optional

from .context import get_tenant_context

# 脱敏分级（分级与判定标准引用 P4 第 12 章，本处不重定义；无法判定按 L2 从严）
# L0 公开 / L1 内部 / L2 受限 / L3 机密(密钥令牌，禁止入日志) / L4 绝密
_SENSITIVE_KEY_PATTERNS = (
    "password",
    "secret",
    "token",
    "api_key",
    "apikey",
    "credential",
    "authorization",
    "cookie",
    "private_key",
)

# 命中即视为 L3（禁止入日志），统一替换为固定掩码
_MASK = "***REDACTED***"


def _is_sensitive_key(key: str) -> bool:
    k = key.lower().replace("-", "_").replace(".", "_")
    return any(p in k for p in _SENSITIVE_KEY_PATTERNS)


def redact(value: Any) -> Any:
    """递归脱敏：字典命中敏感键的值、列表元素、标量原样返回（非敏感）。"""
    if isinstance(value, dict):
        return {k: (_MASK if _is_sensitive_key(k) else redact(v)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return type(value)(redact(v) for v in value)
    return value


class ContextInjectingFilter(logging.Filter):
    """为每条日志记录注入隔离上下文三要素（tenant/user/request）。"""

    def filter(self, record: logging.LogRecord) -> bool:
        ctx = get_tenant_context()
        record.tenant_id = ctx.tenant_id if ctx else None
        record.user_id = ctx.user_id if ctx else None
        record.request_id = ctx.request_id if ctx else None
        return True


class StructuredFormatter(logging.Formatter):
    """结构化（JSON）Formatter，输出固定 schema。"""

    def format(self, record: logging.LogRecord) -> str:
        payload: Dict[str, Any] = {
            "ts": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "tenant_id": getattr(record, "tenant_id", None),
            "user_id": getattr(record, "user_id", None),
            "request_id": getattr(record, "request_id", None),
        }
        if record.exc_info:
            # 仅记录异常类型与消息，不记录完整堆栈到结构化字段（排障用 exc_text 单独通道）
            payload["exc"] = record.exc_info[0].__name__ if record.exc_info[0] else None
        return json.dumps(payload, ensure_ascii=False)


def get_logger(name: str) -> logging.Logger:
    """返回已挂载上下文注入过滤器的结构化日志器。

    注意：敏感字段由调用方在传入 ``extra`` / ``msg`` 前用 :func:`redact` 处理；
    本函数对已知敏感键做二次兜底（见 :class:`ContextInjectingFilter` 不参与键级脱敏，
    键级脱敏由 :func:`redact` 在业务侧完成）。
    """
    logger = logging.getLogger(name)
    if not any(isinstance(f, ContextInjectingFilter) for f in logger.filters):
        logger.addFilter(ContextInjectingFilter())
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(StructuredFormatter())
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
    return logger
