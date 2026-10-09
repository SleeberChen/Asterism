"""APP-COMPLIANCE 领域模型单元测试（纯数据，无 IO / 无框架依赖）。

覆盖 `asterism/domain/compliance/model.py`：鉴权判定、审计事件、break-glass 五要素。
"""
from asterism.domain.compliance.model import AuditEvent, BreakGlassGrant, Decision


def test_decision_carries_full_judgement_context():
    d = Decision(
        allowed=True,
        reason="matched policy",
        tenant_id="t-1",
        user_id="u-1",
        resource="rag",
        action="read",
    )
    assert d.allowed is True
    assert (d.tenant_id, d.user_id, d.resource, d.action) == ("t-1", "u-1", "rag", "read")
    assert d.reason == "matched policy"


def test_decision_allows_anonymous_user():
    d = Decision(
        allowed=False,
        reason="no user",
        tenant_id="t-1",
        user_id=None,
        resource="rag",
        action="read",
    )
    assert d.allowed is False
    assert d.user_id is None


def test_audit_event_defaults():
    e = AuditEvent(
        tenant_id="t-1", user_id="u-1", action="read", resource="rag", outcome="allow"
    )
    assert e.request_id is None
    assert e.detail == {}


def test_audit_event_detail_is_not_shared_between_instances():
    """`field(default_factory=dict)` 必须逐实例新建，避免可变默认值共享（防跨租户串数据）。"""
    e1 = AuditEvent(
        tenant_id="t-1", user_id="u-1", action="read", resource="rag", outcome="allow"
    )
    e2 = AuditEvent(
        tenant_id="t-1", user_id="u-1", action="read", resource="rag", outcome="deny"
    )
    e1.detail["k"] = "v"
    assert e1.detail == {"k": "v"}
    assert e2.detail == {}


def test_break_glass_grant_defaults_satisfy_five_factors():
    """CON06 五要素：审批 + 只读 + 脱敏 + 短时效 + 强审计。"""
    g = BreakGlassGrant(
        tenant_id="t-1",
        user_id="u-1",
        resource="rag",
        approver="a-1",
        ticket_id="T-1",
        ttl_seconds=900,
    )
    assert (g.approver, g.ticket_id) == ("a-1", "T-1")
    assert g.read_only is True
    assert g.redacted is True
    assert g.audit_required is True
    assert g.ttl_seconds == 900


def test_break_glass_grant_defaults_are_overridable_explicitly():
    g = BreakGlassGrant(
        tenant_id="t-1",
        user_id="u-1",
        resource="rag",
        approver="a-1",
        ticket_id="T-1",
        ttl_seconds=60,
        read_only=False,
        redacted=False,
        audit_required=False,
    )
    assert (g.read_only, g.redacted, g.audit_required) == (False, False, False)
