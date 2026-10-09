"""安全合规领域模型（纯数据，无 IO、无框架依赖）。

承载 `BC-COMPLIANCE`：鉴权判定、审计事件、break-glass 五要素（P3 §3 / P0 CON06）。
模型内不含凭据 / 令牌（TC-14：凭据不得入模型与日志）。

**分层建模规范**：领域层实体 / 值对象用 ``dataclass``，不引入 Pydantic（保持领域纯净）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class Decision:
    """鉴权判定结果。"""

    allowed: bool
    reason: str
    tenant_id: str
    user_id: Optional[str]
    resource: str
    action: str


@dataclass
class AuditEvent:
    """审计事件（等保二级：留存 ≥180 天；本骨架为进程内演示存储）。"""

    tenant_id: str
    user_id: Optional[str]
    action: str
    resource: str
    outcome: str  # allow / deny / error
    request_id: Optional[str] = None
    detail: Dict[str, Any] = field(default_factory=dict)


@dataclass
class BreakGlassGrant:
    """break-glass 授权（CON06 五要素齐全方可生效）。

    五要素：审批（approver / ticket_id）+ 只读（read_only）+ 脱敏（redacted）
    + 短时效（ttl_seconds）+ 强审计（audit_required）。
    """

    tenant_id: str
    user_id: str
    resource: str
    approver: str
    ticket_id: str
    ttl_seconds: int
    read_only: bool = True
    redacted: bool = True
    audit_required: bool = True
