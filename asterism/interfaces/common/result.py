"""统一 RESTful 响应信封（强制规范：全局所有非 204 / 非健康检查响应必须包裹）。

形态：``{code, message, data, request_id}``
- 成功：``code="0"``、``message="ok"``、``data=<业务负载>``、``request_id=<链路标识>``
- 失败：``code=AST-ERR-*``、``message=<用户可读信息>``、``data=null``、``request_id=<链路标识>``

使用约定（强制）：
- 接口路由的成功响应一律返回 ``ApiResult[<业务 Schema>]``（``response_model`` 同步设为
  ``ApiResult[...]``），业务负载置于 ``data``；不要在 ``data`` 之外再平铺业务字段。
- 失败由全局异常处理器（``asterism/main.py``）统一把 ``AsterismError`` 映射为本信封，
  路由内**不要**再手写 ``JSONResponse(exc.to_dict())``（已移除）。
- 204 No Content 与 ``/healthz`` 探针按设计豁免包裹（无响应体）。
- 流式（SSE）成功帧为 ``ApiResult[<ChunkSchema>]`` 的逐帧序列化；错误帧为
  ``ApiResult.fail(...)``（``event: error``），保持与 JSON 接口同一信封。
"""

from __future__ import annotations

from typing import Generic, Optional, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class ApiResult(BaseModel, Generic[T]):
    """统一响应信封（见模块 docstring 的强制规范）。"""

    code: str = "0"
    message: str = "ok"
    data: Optional[T] = None
    request_id: Optional[str] = None

    @classmethod
    def ok(
        cls,
        data: Optional[T] = None,
        *,
        request_id: Optional[str] = None,
        message: str = "ok",
    ) -> "ApiResult[T]":
        return cls(code="0", message=message, data=data, request_id=request_id)

    @classmethod
    def fail(
        cls,
        code: str,
        message: Optional[str] = None,
        *,
        request_id: Optional[str] = None,
        data: Optional[T] = None,
    ) -> "ApiResult[T]":
        return cls(code=code, message=message or code, data=data, request_id=request_id)
