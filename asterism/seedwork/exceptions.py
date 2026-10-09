"""异常体系（P5 §14.4.2）。

分类：
- 业务异常 ``BusinessError``：可预期、可提示用户。
- 系统异常 ``SystemError``：不可预期、需告警。
- 外部依赖异常 ``ExternalDependencyError``：供应商 / 中间件，须带降级或回退路径。

约定：必带错误码 + 用户可读信息 + 链路标识；内部上下文写入日志，不写入响应体（TC-16）。
禁止吞异常 / 空 except / 返回 None 掩盖失败（TC-15）。
"""

from __future__ import annotations

from typing import Optional

from .errors import http_status_for, message_for


class AsterismError(Exception):
    """统一异常基类，携带 ``AST-ERR`` 错误码与 HTTP 映射。"""

    def __init__(
        self,
        code: str,
        message: Optional[str] = None,
        *,
        request_id: Optional[str] = None,
        cause: Optional[BaseException] = None,
    ) -> None:
        self.code = code
        self.message = message or message_for(code)
        self.request_id = request_id
        self.http_status = http_status_for(code)
        super().__init__(self.message)
        if cause is not None:
            self.__cause__ = cause

    def to_dict(self) -> dict:
        """对外响应体（不含堆栈 / 内网地址 / SQL 原文，TC-16）。"""
        return {
            "code": self.code,
            "message": self.message,
            "request_id": self.request_id,
        }


class BusinessError(AsterismError):
    """业务异常：可预期、可提示用户（映射 2xxx / 3xxx）。"""


class SystemError(AsterismError):
    """系统异常：不可预期、需告警（映射 5xxx）。"""


class ExternalDependencyError(AsterismError):
    """外部依赖异常：供应商 / 中间件（映射 4xxx）；须由调用方提供降级或回退路径。"""
