"""APP-COMPLIANCE 装配（安全合规骨架，横切基座）。"""

from __future__ import annotations

from fastapi import FastAPI

from asterism.application.compliance.use_case import (
    AuditQueryUseCase,
    AuthorizeUseCase,
    BreakGlassUseCase,
)
from asterism.infrastructure.compliance.audit import InMemoryAuditStore
from asterism.infrastructure.compliance.authz import InMemoryAuthzProvider
from asterism.interfaces.compliance.router import router as compliance_router


def wire_compliance(app: FastAPI) -> None:
    """装配安全合规应用：审计存储 + 鉴权实现 + 用例 + 路由。

    本应用为**横切基座**：其余应用经 ``interfaces.compliance.deps`` 复用其鉴权判定，
    故须装配在依赖鉴权的应用之前（见 ``registry.APP_WIRINGS`` 顺序）。
    """
    audit = InMemoryAuditStore()
    authz = InMemoryAuthzProvider()

    app.include_router(compliance_router)
    app.state.compliance_authorize_use_case = AuthorizeUseCase(authz=authz, audit=audit)
    app.state.compliance_audit_query_use_case = AuditQueryUseCase(audit=audit)
    app.state.compliance_break_glass_use_case = BreakGlassUseCase(audit=audit)
