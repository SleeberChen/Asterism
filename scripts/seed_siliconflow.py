"""通过已落地的 BC-MODEL 端点，将「硅基流动 / GLM-Z1-9B-0414」厂商与模型插入业务库。

合规要点（IN3 / TC-01 / TC-02 / L3 密文定位引用）：
- API 秘钥明文**绝不**写入本脚本，也**绝不**写入数据库。
- 数据库 ``asterism_vendors.credential_handle`` 仅存 L3 密文定位引用
  ``env://SILICONFLOW_API_KEY``；真实秘钥只存在于部署环境的密钥后端
  （环境变量 SILICONFLOW_API_KEY / KMS / Vault）。
- 运行时模型供应商插件按 ``credential_handle`` 定位引用取秘钥；应用代码不读明文
  （``SecretRef`` 只写不读，可读次数 = 0）。

运行（默认本地 sqlite 种子库；同一份脚本可指向生产 MySQL）：
    uv run python scripts/seed_siliconflow.py
    # 指向生产 MySQL（并在真实租户下写入）：
    ASTERISM_SEED_DB_URL="mysql+aiomysql://user:pwd@host/asterism_business" \
    ASTERISM_SEED_TENANT="<真实租户ID>" \
    uv run python scripts/seed_siliconflow.py

环境变量：
- ASTERISM_SEED_DB_URL  : 业务库 URL（默认 sqlite 文件 scripts/seed_business.db）
- ASTERISM_SEED_TENANT  : 租户 ID（默认 t-default，按行级隔离字段写入）
- ASTERISM_SEED_DRY_RUN : 设非空则只打印请求体、不真正写入
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path

# 必须在导入 asterism 之前决定业务库 URL（engine 懒加载时读取 ASTERISM__DATABASE__URL）
DEFAULT_DB = (Path(__file__).resolve().parent / "seed_business.db").as_posix()
DB_URL = os.environ.get("ASTERISM_SEED_DB_URL", f"sqlite+aiosqlite:///{DEFAULT_DB}")
os.environ["ASTERISM__DATABASE__URL"] = DB_URL

# 直接导入：若 TestClient 不可用，收集即失败（符合 TC-21「环境不可用判失败」）
from fastapi.testclient import TestClient
from sqlalchemy import text

from asterism.infrastructure.persistence.engine import get_business_engine, reset_business_engine
from asterism.main import create_app

TENANT = os.environ.get("ASTERISM_SEED_TENANT", "t-default")
DRY = bool(os.environ.get("ASTERISM_SEED_DRY_RUN"))

# 合规：仅密文定位引用；秘钥明文只存在于部署密钥后端（SILICONFLOW_API_KEY）
CRED_HANDLE = "env://SILICONFLOW_API_KEY"

VENDOR = {
    "vendor_id": "siliconflow",
    "plugin_registration_ref": "siliconflow-openai",
    "name": "硅基流动",
    "access_protocol": "openai",
    "base_url": "https://api.siliconflow.cn/v1",
    "credential_handle": CRED_HANDLE,
    "default_timeout_budget_ms": 60000,
}
MODEL = {
    "model_id": "THUDM/GLM-Z1-9B-0414",
    "name": "GLM-Z1-9B-0414",
    "context_window": 131072,
    "modalities": ["text"],
    "pricing_note": "$0.09/1M input, $0.09/1M output (约 ¥0.65/1M)；来源 SiliconFlow 2026 定价",
    "is_default": True,
}
HEADERS = {"X-Tenant-Id": TENANT, "X-User-Id": "admin"}


def _vendor_exists(c: TestClient, vid: str) -> bool:
    return c.get(f"/api/v1/models/vendors/{vid}", headers=HEADERS).status_code == 200


async def _read_stored_handle() -> tuple[str, str, str] | None:
    """直连库读取已落地的 credential_handle / tenant_id / status（合规核验用）。"""
    engine = await get_business_engine()
    async with engine.connect() as conn:
        res = await conn.execute(
            text(
                "SELECT credential_handle, tenant_id, status "
                "FROM asterism_vendors WHERE vendor_id=:v"
            ),
            {"v": VENDOR["vendor_id"]},
        )
        row = res.fetchone()
    return tuple(row) if row else None  # type: ignore[arg-type]


def main() -> int:
    if DRY:
        print("[DRY-RUN] DB_URL:", DB_URL, "TENANT:", TENANT)
        print("[DRY-RUN] VENDOR:", VENDOR)
        print("[DRY-RUN] MODEL :", MODEL)
        print("[DRY-RUN] 注意：credential_handle 为 L3 引用，秘钥明文须由密钥后端提供，不在此落库")
        return 0

    reset_business_engine()
    app = create_app()
    with TestClient(app) as c:
        # 1) 厂商：幂等（已存在则跳过）
        if _vendor_exists(c, VENDOR["vendor_id"]):
            print(f"[SKIP] 厂商已存在: {VENDOR['vendor_id']}")
        else:
            r = c.post("/api/v1/models/vendors", headers=HEADERS, json=VENDOR)
            print("POST /vendors ->", r.status_code, r.json())
            if r.status_code != 201:
                return 1

        # 2) 模型：幂等（同厂商下已存在则跳过）
        listed = c.get(
            f"/api/v1/models/vendors/{VENDOR['vendor_id']}/models", headers=HEADERS
        )
        existing = {m["model_id"] for m in listed.json().get("data", [])}
        if MODEL["model_id"] in existing:
            print(f"[SKIP] 模型已存在: {MODEL['model_id']}")
        else:
            r2 = c.post(
                f"/api/v1/models/vendors/{VENDOR['vendor_id']}/models",
                headers=HEADERS,
                json=MODEL,
            )
            print("POST /vendors/siliconflow/models ->", r2.status_code, r2.json())
            if r2.status_code != 201:
                return 1

        # 3) 校验：读回厂商（含嵌套模型）
        r3 = c.get(f"/api/v1/models/vendors/{VENDOR['vendor_id']}", headers=HEADERS)
        data = r3.json()["data"]
        print("GET /vendors/siliconflow ->", r3.status_code)
        print("  vendor      :", data["vendor_id"], data["name"], "status=", data["status"])
        print("  models      :", [(m["model_id"], m["is_default"]) for m in data["models"]])

    # 4) 直连库核验：credential_handle 仅为 L3 引用，绝无明文秘钥（响应体不含该字段，故直读库）
    row = asyncio.run(_read_stored_handle())
    if row is None:
        print("[WARN] 未在库中读到厂商行，插入可能未持久化")
        return 1
    handle, tenant, status = row
    print("DB 核验:")
    print("  stored tenant_id  :", tenant)
    print("  stored status     :", status)
    print("  stored cred_handle:", handle)
    assert handle == CRED_HANDLE, f"credential_handle 异常: {handle}"
    assert not handle.startswith("sk-"), "致命：秘钥明文落入数据库！"
    print("  [合规] credential_handle 仅为密文定位引用，秘钥明文未落库 ✅")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
