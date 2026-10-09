"""鉴权判定实现（演示用，实现 ``AuthzPort``）。

权威写者＝`APP-COMPLIANCE`（P3 §5）；其余应用经契约 IC-07 只读判定。
生产：替换为真实权限服务；并入星云形态对接星云公共权限（`BC-PERM`）。
"""

from __future__ import annotations

from typing import Optional

from asterism.domain.compliance.model import Decision
from asterism.domain.compliance.ports import AuthzPort

# 演示策略：需管理员角色的动作
_ADMIN_ACTIONS = frozenset({"admin", "grant", "break_glass"})
_ADMIN_USER = "admin"


class InMemoryAuthzProvider(AuthzPort):
    """确定性演示策略：未认证主体即拒绝；管理员动作须 admin 用户。"""

    def authorize(
        self,
        *,
        tenant_id: str,
        user_id: Optional[str],
        resource: str,
        action: str,
    ) -> Decision:
        common = {
            "tenant_id": tenant_id,
            "user_id": user_id,
            "resource": resource,
            "action": action,
        }
        if not user_id:
            return Decision(allowed=False, reason="未提供用户标识（未认证）", **common)
        if action in _ADMIN_ACTIONS and user_id != _ADMIN_USER:
            return Decision(allowed=False, reason="功能权限不足（该动作需管理员）", **common)
        return Decision(allowed=True, reason="允许", **common)
