"""seedwork 错误码与异常单元测试。"""

from __future__ import annotations

from asterism.seedwork.errors import http_status_for, is_registered, message_for
from asterism.seedwork.exceptions import AsterismError, BusinessError


def test_registered_codes_and_http_mapping():
    assert is_registered("AST-ERR-3001")
    assert http_status_for("AST-ERR-3001") == 400
    assert http_status_for("AST-ERR-2001") == 401
    assert message_for("AST-ERR-2004")


def test_unknown_code_defaults_internal():
    # 未登记错误码默认映射 500，不泄露未知码含义
    assert http_status_for("AST-ERR-9999") == 500


def test_exception_carries_code_and_http():
    exc = BusinessError("AST-ERR-3001")
    assert exc.code == "AST-ERR-3001"
    assert exc.http_status == 400
    body = exc.to_dict()
    assert body["code"] == "AST-ERR-3001"
    assert "stack" not in body and "traceback" not in body  # 响应体不含内部细节（TC-16）


def test_cause_chain_preserved():
    try:
        raise RuntimeError("boom")
    except RuntimeError as e:
        wrapped = AsterismError("AST-ERR-5001", cause=e)
    assert isinstance(wrapped.__cause__, RuntimeError)
