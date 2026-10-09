"""审计存储实现（演示用，实现 ``AuditPort``）。

等保二级：审计留存 ≥180 天（``RETENTION_DAYS``）。本骨架为**进程内演示存储**，
生产须替换为可持久化、按租户隔离、到期自动清理的审计后端（P5 / P4 第 12 章）。
"""

from __future__ import annotations

from typing import Dict, List, Optional

from asterism.domain.compliance.model import AuditEvent
from asterism.domain.compliance.ports import AuditPort
from asterism.seedwork.logging import get_logger, redact

logger = get_logger(__name__)

RETENTION_DAYS = 180  # 等保二级：审计留存 ≥180 天


class InMemoryAuditStore(AuditPort):
    """进程内审计存储（租户隔离；明细落库前强制脱敏，TC-14 / L3）。"""

    def __init__(self) -> None:
        self._by_tenant: Dict[str, List[AuditEvent]] = {}

    def write(self, event: AuditEvent) -> None:
        # 明细脱敏后再存储（凭据 / 令牌类键一律掩码，TC-14）
        event.detail = redact(event.detail)
        self._by_tenant.setdefault(event.tenant_id, []).append(event)
        logger.info(
            "审计留痕", extra={"action": event.action, "outcome": event.outcome}
        )

    def query(
        self, *, tenant_id: str, action: Optional[str] = None, limit: int = 50
    ) -> List[AuditEvent]:
        # 仅返回本租户事件（八通道隔离）
        events = self._by_tenant.get(tenant_id, [])
        if action:
            events = [e for e in events if e.action == action]
        return list(events[-limit:])
