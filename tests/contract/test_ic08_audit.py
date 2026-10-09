"""契约测试 `T-CONTRACT-08` → `IC-08` 审计埋点契约。

测试意图（P3 02-应用间契约.md）：
- 受控操作审计覆盖率 = 100%（漏审 = 0）；
- 审计记录不可被应用侧修改。
"""
from __future__ import annotations

import json

from asterism.application.compliance.use_case import AuthorizeUseCase
from asterism.domain.compliance.model import AuditEvent, Decision
from asterism.infrastructure.compliance.audit import RETENTION_DAYS, InMemoryAuditStore

DEMO_TENANT = "demo-tenant"


class _StubAuthz:
    """判定桩：按构造参数固定返回 allow / deny。"""

    def __init__(self, allowed: bool) -> None:
        self._allowed = allowed

    def authorize(self, *, tenant_id, user_id, resource, action) -> Decision:
        return Decision(
            allowed=self._allowed,
            reason="stub",
            tenant_id=tenant_id,
            user_id=user_id,
            resource=resource,
            action=action,
        )


def test_controlled_operation_is_always_audited(tenant_ctx):
    """每次鉴权判定（受控操作）必留痕：漏审 = 0。"""
    audit = InMemoryAuditStore()
    uc = AuthorizeUseCase(authz=_StubAuthz(True), audit=audit)

    uc.execute("rag", "read")
    uc.execute("rag", "write")

    events = audit.query(tenant_id=DEMO_TENANT)
    assert len(events) == 2, "受控操作存在漏审"
    assert [e.action for e in events] == ["read", "write"]


def test_denied_decision_is_audited_too(tenant_ctx):
    """拒绝同样是受控操作，必须留痕（outcome=deny）。"""
    audit = InMemoryAuditStore()
    uc = AuthorizeUseCase(authz=_StubAuthz(False), audit=audit)
    uc.execute("rag", "read")
    assert audit.query(tenant_id=DEMO_TENANT)[0].outcome == "deny"


def test_audit_is_tenant_scoped(tenant_ctx):
    """审计查询仅返回本租户事件（八通道隔离）。"""
    audit = InMemoryAuditStore()
    AuthorizeUseCase(authz=_StubAuthz(True), audit=audit).execute("rag", "read")
    assert len(audit.query(tenant_id=DEMO_TENANT)) == 1
    assert audit.query(tenant_id="other-tenant") == []


def test_audit_retention_meets_grade_two_requirement():
    """等保二级：审计留存 ≥ 180 天。"""
    assert RETENTION_DAYS >= 180


def test_audit_detail_is_redacted_before_persist(tenant_ctx):
    """明细落库前强制脱敏（TC-14 / L3）：凭据类值不得原文入库。"""
    audit = InMemoryAuditStore()
    audit.write(
        AuditEvent(
            tenant_id=DEMO_TENANT,
            user_id="u1",
            action="read",
            resource="rag",
            outcome="allow",
            detail={"api_key": "sk-secret-plaintext"},
        )
    )
    stored = audit.query(tenant_id=DEMO_TENANT)[0]
    assert "sk-secret-plaintext" not in json.dumps(stored.detail, ensure_ascii=False)
