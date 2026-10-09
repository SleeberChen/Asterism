"""开关白名单校验（P5 TC-23 / 附录 B）。

TC-23：开关名须来自项目开关白名单，禁止自创；引用点 vs 白名单求差集 = 0。
当前附录 B（开关与配置契约）尚未产出 → 前置未完成 → 记 WARN（与本册 §7 同口径）。
本模块给出最小白名单作为骨架起点，待附录 B 产出后补全并消除 WARN。
"""

from __future__ import annotations

from asterism.seedwork.exceptions import BusinessError

# 最小白名单（骨架起点；附录 B 产出后须同步扩展并关闭 WARN）
# 注：以下仅为示例开关，真实开关清单以附录 B 为唯一来源。
FEATURE_FLAG_WHITELIST = frozenset(
    {
        "rag_demo_enabled",       # 示范 RAG 应用开关
        "memory_compression",      # 会话记忆压缩
        "strict_tenant_isolation",  # 严格租户隔离（缺失即拒绝）
    }
)


def is_registered(flag: str) -> bool:
    return flag in FEATURE_FLAG_WHITELIST


def validate_flag(flag: str) -> None:
    """校验开关名是否在白名单内；不在则抛 AST-ERR（TC-23）。

    紧急热修经架构组批准可 24 小时内补登记（登记方式：追加到 FEATURE_FLAG_WHITELIST
    并回写附录 B）。
    """
    if flag not in FEATURE_FLAG_WHITELIST:
        # 使用 3xxx 参数类错误码表达「未知开关」
        raise BusinessError("AST-ERR-3001", message=f"未知功能开关：{flag!r}（须先登记于开关白名单）")
