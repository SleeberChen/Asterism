"""APP-COMPLIANCE 端口契约单元测试（runtime_checkable Protocol 结构校验）。

覆盖 `asterism/domain/compliance/ports.py`：AuthzPort / AuditPort。
权威写者＝APP-COMPLIANCE（P3 §5），其余应用经契约只读，禁止各自实现鉴权。
"""
from asterism.domain.compliance.model import AuditEvent, Decision
from asterism.domain.compliance.ports import AuditPort, AuthzPort


class _FakeAuthz:
    def __init__(self, allowed):
        self._allowed = allowed
        self.calls = []

    def authorize(self, *, tenant_id, user_id, resource, action):
        self.calls.append((tenant_id, user_id, resource, action))
        return Decision(
            allowed=self._allowed,
            reason="stub",
            tenant_id=tenant_id,
            user_id=user_id,
            resource=resource,
            action=action,
        )


class _FakeAudit:
    def __init__(self):
        self.events = []

    def write(self, event):
        self.events.append(event)

    def query(self, *, tenant_id, action=None, limit=50):
        matched = [
            e
            for e in self.events
            if e.tenant_id == tenant_id and (action is None or e.action == action)
        ]
        return matched[:limit]


def test_authz_port_satisfied_by_duck_typed_impl():
    impl = _FakeAuthz(True)
    assert isinstance(impl, AuthzPort)
    d = impl.authorize(tenant_id="t-1", user_id="u-1", resource="rag", action="read")
    assert d.allowed is True
    assert impl.calls == [("t-1", "u-1", "rag", "read")]


def test_authz_port_rejects_wrong_shape():
    assert not isinstance(object(), AuthzPort)


def test_audit_port_write_then_query_is_tenant_scoped():
    impl = _FakeAudit()
    assert isinstance(impl, AuditPort)
    impl.write(
        AuditEvent(
            tenant_id="t-1", user_id="u-1", action="read", resource="rag", outcome="allow"
        )
    )
    impl.write(
        AuditEvent(
            tenant_id="t-2", user_id="u-2", action="read", resource="rag", outcome="deny"
        )
    )
    assert len(impl.query(tenant_id="t-1")) == 1
    assert len(impl.query(tenant_id="t-2")) == 1
    assert impl.query(tenant_id="t-1", action="write") == []


def test_audit_port_query_respects_limit():
    impl = _FakeAudit()
    for _ in range(5):
        impl.write(
            AuditEvent(
                tenant_id="t-1", user_id="u-1", action="read", resource="rag", outcome="allow"
            )
        )
    assert len(impl.query(tenant_id="t-1", limit=2)) == 2
