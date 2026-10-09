"""应用装配区（组合根支撑，`root` 区）。

**为何独立成区（分层硬约束）**：装配一个应用需要同时 import
`interfaces`（路由）、`application`（用例）、`infrastructure`（适配器）三层，
而依赖矩阵禁止 `interfaces → infrastructure`、`application → infrastructure`，
因此装配代码**不能放进任何一层**，只能位于四层之外。

本区与 `main.py` 同属「组合根」语义延伸：允许依赖全部层（P5 TC-09 例外，
GATE-04 按 `root` 豁免）。

**纪律（防止本区退化成逃生舱）**：
- 本区**只做装配**（`include_router` + 装配 `app.state.*`），**禁止写业务逻辑**；
- 新增应用＝新增 `bootstrap/<app>.py` 并在 `registry.APP_WIRINGS` 登记，
  不改动 `main.py`（开闭原则）。
"""

from .registry import APP_WIRINGS, register_apps

__all__ = ["APP_WIRINGS", "register_apps"]
