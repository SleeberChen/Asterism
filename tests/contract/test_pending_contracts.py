"""契约测试缺口登记：`T-CONTRACT-03`~`06`、`09`、`11`、`12`。

**诚实声明（D6：不得把"未实现"写成"已验证"）**

P8 骨架本期仅落地 rag / model / compliance / system 四个切片与插件内核，
下列契约的**生产方应用尚未实现**，契约无可验证对象。故不编写"伪通过"断言，
而是显式登记为 pending 并注明理由与关闭时点（P6 详细设计 / P11 验收）。

已落真实断言的契约：`T-CONTRACT-01`/`02`/`07`/`08`/`10`。
"""
from __future__ import annotations

import pytest

IMPLEMENTED = [
    "T-CONTRACT-01",
    "T-CONTRACT-02",
    "T-CONTRACT-07",
    "T-CONTRACT-08",
    "T-CONTRACT-10",
]

# 契约测试 -> (对应契约, 未实现原因)
PENDING = {
    "T-CONTRACT-03": ("IC-03", "APP-TOOL 未落地：工具调用请求/响应、权限校验与审计载荷无可验证对象"),
    "T-CONTRACT-04": ("IC-04", "APP-SKILL 未落地：受管控来源技能加载/启停/卸载无可验证对象"),
    "T-CONTRACT-05": ("IC-05", "APP-MEMORY 未落地：会话记忆读写、长度上限与保留策略无可验证对象"),
    "T-CONTRACT-06": ("IC-06", "APP-FACTORY 未落地：应用骨架创建、默认链路装配无可验证对象"),
    "T-CONTRACT-09": ("IC-09", "APP-OBSERV 未落地：链路标识贯穿、指标上报与失败计数无可验证对象"),
    "T-CONTRACT-11": ("IC-11", "APP-CORE 编排底座未落地：节点契约校验与装配回滚无可验证对象"),
    "T-CONTRACT-12": ("IC-12", "APP-SYSTEM 仅落地目录查询：自审自批拒绝、用户停用后会话失效未实现"),
}

ALL_CONTRACTS = [f"T-CONTRACT-{i:02d}" for i in range(1, 13)]


def test_all_twelve_contracts_are_accounted():
    """契约测试覆盖登记：12 条全部有归属（已实现断言 or 已登记 pending），缺项 = 0。"""
    accounted = set(IMPLEMENTED) | set(PENDING)
    missing = sorted(set(ALL_CONTRACTS) - accounted)
    unknown = sorted(accounted - set(ALL_CONTRACTS))
    assert missing == [], f"契约测试缺项（GATE-10 要求 缺项=0）：{missing}"
    assert unknown == [], f"登记了不存在的契约编号：{unknown}"


@pytest.mark.parametrize("contract_id", sorted(PENDING))
def test_pending_contract(contract_id: str) -> None:
    """占位：显式跳过并登记理由，等待 P6 实现 / P11 验收时补真实断言。"""
    ic, reason = PENDING[contract_id]
    pytest.skip(f"{contract_id}（{ic}）待 P6/P11：{reason}")
