-- =====================================================================
-- Asterism BC-MODEL 物理模型 DDL（V1.0.0，SQLite 方言）
-- 来源：asterism-docs/20-design/P6-详细设计/bc-model/逻辑数据模型.md
-- 落点约定：<repo>/db/migration/<dialect>/V1.0.0__{领域}.sql（参照 Nebula Flyway 版本控制）
-- 硬约束（DDD 战术设计）：
--   1) 1 聚合 = 1 主表（vendors / prompt_templates 为聚合根主表）
--   2) 聚合根主表含 version 乐观锁（冲突映射 409）
--   3) 跨聚合只存 ID；models.vendor_id 为聚合内关联（同一 BC，非跨 BC 外键）
--   4) tenant_id 行级隔离 + 索引
--   5) 凭据句柄 credential_handle 仅密文定位引用（L3 不落明文）
-- 类型约定（SQLite 方言）：
--   JSON 列以 TEXT 存储（SQLAlchemy JSON 类型序列化/反序列化）
--   BOOLEAN 以 INTEGER(0/1) 存储
-- 幂等：全部 IF NOT EXISTS；重放安全（apply_migrations 按 schema_version 去重）
-- =====================================================================

-- 2.1 厂商聚合根主表（ET-03 演进：Vendor 聚合根 = 身份 + VendorConfig(VO) + models）
CREATE TABLE IF NOT EXISTS vendors (
    vendor_id               TEXT    NOT NULL,
    plugin_registration_ref TEXT   NOT NULL,
    name                   TEXT    NOT NULL,
    status                 TEXT    NOT NULL DEFAULT '停用',
    tenant_id              TEXT    NOT NULL,
    version                INTEGER NOT NULL DEFAULT 1,
    access_protocol        TEXT    NOT NULL,
    base_url               TEXT    NOT NULL,
    credential_handle      TEXT    NOT NULL,
    default_timeout_budget_ms INTEGER NOT NULL,
    failover_target_ref    TEXT    DEFAULT NULL,
    PRIMARY KEY (vendor_id),
    UNIQUE (plugin_registration_ref)
);
CREATE INDEX idx_vendors_tenant ON vendors (tenant_id);
CREATE INDEX idx_vendors_status ON vendors (status);

-- 2.2 模型（聚合内实体，从属于 Vendor；vendor_id 聚合内关联）
CREATE TABLE IF NOT EXISTS models (
    model_id               TEXT    NOT NULL,
    vendor_id              TEXT    NOT NULL,
    tenant_id              TEXT    NOT NULL,
    name                   TEXT    NOT NULL,
    capability_context_window INTEGER NOT NULL,
    capability_modalities  TEXT    NOT NULL,
    capability_pricing     TEXT    NOT NULL DEFAULT '',
    is_default             INTEGER NOT NULL DEFAULT 0,
    prompt_template_ids    TEXT    NOT NULL,
    PRIMARY KEY (model_id),
    CONSTRAINT fk_models_vendor FOREIGN KEY (vendor_id) REFERENCES vendors (vendor_id)
);
CREATE INDEX idx_models_vendor ON models (vendor_id);
CREATE INDEX idx_models_tenant ON models (tenant_id);

-- 2.3 提示词模板（独立聚合根，可跨 Model / 跨 BC 复用，需稳定 ID 引用）
CREATE TABLE IF NOT EXISTS prompt_templates (
    template_id            TEXT    NOT NULL,
    name                   TEXT    NOT NULL,
    content                TEXT    NOT NULL,
    variables              TEXT    NOT NULL,
    version                INTEGER NOT NULL DEFAULT 1,
    model_affinity         TEXT    DEFAULT NULL,
    status                 TEXT    NOT NULL DEFAULT '启用',
    tenant_id              TEXT    NOT NULL,
    PRIMARY KEY (template_id)
);
CREATE INDEX idx_prompt_templates_tenant ON prompt_templates (tenant_id);
CREATE INDEX idx_prompt_templates_name ON prompt_templates (name);
