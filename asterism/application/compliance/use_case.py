"""安全合规用例（应用层门面）。"""

from __future__ import annotations

from typing import List, Optional

from asterism.domain.compliance.model import AuditEvent, BreakGlassGrant, Decision
from asterism.domain.compliance.ports import AuditPort, AuthzPort
from asterism.seedwork.context import require_tenant_context
from asterism.seedwork.exceptions import AsterismError, BusinessError, SystemError


class AuthorizeUseCase:
    """鉴权判定：注入隔离上下文 → 端口判定 → 判定结果一律留痕（强审计）。"""

    def __init__(self, authz: AuthzPort, audit: AuditPort) -> None:
        self._authz = authz
        self._audit = audit

    def execute(
        self, resource: str, action: str, *, request_id: Optional[str] = None
    ) -> Decision:
        # 隔离上下文缺失即拒绝（TC-12：框架统一注入；缺失抛 AST-ERR-2004）
        ctx = require_tenant_context()

        if not resource or not action:
            raise BusinessError("AST-ERR-3001", message="资源与动作不能为空")
        try:
            decision = self._authz.authorize(
                tenant_id=ctx.tenant_id,
                user_id=ctx.user_id,
                resource=resource,
                action=action,
            )
        except AsterismError:
            raise  # 已映射错误直接透传
        except Exception as exc:  # 意外：包装为内部错误，保留因果链，不吞（TC-15）
            raise SystemError("AST-ERR-5001", request_id=request_id, cause=exc) from exc

        self._audit.write(
            AuditEvent(
                tenant_id=ctx.tenant_id,
                user_id=ctx.user_id,
                action=action,
                resource=resource,
                outcome="allow" if decision.allowed else "deny",
                request_id=request_id or ctx.request_id,
            )
        )
        return decision


class AuditQueryUseCase:
    """审计查询（仅本租户，八通道隔离；跨租户数据不可见）。"""

    def __init__(self, audit: AuditPort) -> None:
        self._audit = audit

    def execute(
        self, *, action: Optional[str] = None, limit: int = 50
    ) -> List[AuditEvent]:
        ctx = require_tenant_context()
        return self._audit.query(tenant_id=ctx.tenant_id, action=action, limit=limit)


class BreakGlassUseCase:
    """break-glass 授权：五要素齐全方可生效 + 强审计留痕（CON06）。"""

    def __init__(self, audit: AuditPort) -> None:
        self._audit = audit

    def execute(
        self,
        resource: str,
        *,
        approver: str,
        ticket_id: str,
        ttl_seconds: int = 900,
        request_id: Optional[str] = None,
    ) -> BreakGlassGrant:
        ctx = require_tenant_context()

        # 五要素校验（缺一即拒绝）
        if not resource:
            raise BusinessError("AST-ERR-3001", message="目标资源不能为空")
        if not approver or not ticket_id:
            raise BusinessError("AST-ERR-3001", message="break-glass 须提供审批人与审批工单号")
        if not ctx.user_id:
            raise BusinessError("AST-ERR-2001", message="未认证主体不可申请 break-glass")
        if not 1 <= ttl_seconds <= 3600:
            raise BusinessError("AST-ERR-3001", message="break-glass 时效须为 1~3600 秒（短时效）")

        grant = BreakGlassGrant(
            tenant_id=ctx.tenant_id,
            user_id=ctx.user_id,
            resource=resource,
            approver=approver,
            ticket_id=ticket_id,
            ttl_seconds=ttl_seconds,
            read_only=True,  # 只读
            redacted=True,  # 脱敏
            audit_required=True,  # 强审计
        )
        self._audit.write(
            AuditEvent(
                tenant_id=ctx.tenant_id,
                user_id=ctx.user_id,
                action="break_glass",
                resource=resource,
                outcome="allow",
                request_id=request_id or ctx.request_id,
                detail={
                    "approver": approver,
                    "ticket_id": ticket_id,
                    "ttl_seconds": ttl_seconds,
                },
            )
        )
        return grant
