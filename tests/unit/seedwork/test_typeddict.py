"""TypedDict 运行时校验器单元测试。

按分层建模规范，`TypedDict` **不用于领域实体 / 值对象**（那是 dataclass 的职责），
仅用于**跨框架状态结构**（消息状态 / 工作流 State，如 LangGraph 在图节点间传递的 State）。
本测试以一个工作流 State 为例，验证校验器在缺键 / 类型不符时显式拒绝（不吞、不兜底）。
"""

# 注意：本模块不启用 from __future__ import annotations——注解被推迟为字符串后，
# NotRequired[...] 无法被识别，可选键会被误判为必填（实测踩坑）。
from typing import List, NotRequired, Optional, TypedDict

import pytest

from asterism.seedwork.exceptions import BusinessError
from asterism.seedwork.typeddict import validate_typed_dict


class RagWorkflowState(TypedDict):
    """示例：编排工作流在图节点间传递的状态（跨框架状态结构）。"""

    tenant_id: str
    query: str
    chunks: NotRequired[List[str]]
    answer: NotRequired[Optional[str]]


def test_valid_state_passes():
    validate_typed_dict(
        {"tenant_id": "t1", "query": "架构", "chunks": ["a"], "answer": None},
        RagWorkflowState,
        name="RagWorkflowState",
    )


def test_missing_required_key_rejected():
    with pytest.raises(BusinessError) as ei:
        validate_typed_dict({"query": "架构"}, RagWorkflowState, name="RagWorkflowState")
    assert ei.value.code == "AST-ERR-3001"
    assert "tenant_id" in ei.value.message


def test_wrong_type_rejected():
    with pytest.raises(BusinessError) as ei:
        validate_typed_dict(
            {"tenant_id": "t1", "query": 123}, RagWorkflowState, name="RagWorkflowState"
        )
    assert ei.value.code == "AST-ERR-3001"
    assert "类型不符" in ei.value.message


def test_non_dict_rejected():
    with pytest.raises(BusinessError) as ei:
        validate_typed_dict("not-a-dict", RagWorkflowState, name="RagWorkflowState")
    assert ei.value.code == "AST-ERR-3001"


def test_not_a_typeddict_rejected():
    with pytest.raises(BusinessError) as ei:
        validate_typed_dict({}, dict, name="dict")
    assert ei.value.code == "AST-ERR-3001"
