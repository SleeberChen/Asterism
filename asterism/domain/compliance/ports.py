"""安全合规端口（领域层定义，基础设施实现；依赖倒置 TC-09）。"""

from __future__ import annotations

from typing import List, Optional, Protocol, runtime_checkable

from .model import AuditEvent, Decision


@runtime_checkable
class AuthzPort(Protocol):
    """鉴权判定端口。

    权威写者＝`APP-COMPLIANCE`（P3 §5）；其余应用经契约 IC-07 **只读判定**，
    禁止各自实现鉴权（防重复实现、防口径漂移）。
    """

    def authorize(
        self,
        *,
        tenant_id: str,
        user_id: Optional[str],
        resource: str,
        action: str,
    ) -> Decision:
        ...


@runtime_checkable
class AuditPort(Protocol):
    """审计端口：写入留痕 + 租户内查询（等保二级，留存 ≥180 天）。"""

    def write(self, event: AuditEvent) -> None:
        ...

    def query(
        self, *, tenant_id: str, action: Optional[str] = None, limit: int = 50
    ) -> List[AuditEvent]:
        ...
