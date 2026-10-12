-- =====================================================================
-- Asterism BC-MODEL 物理模型 DDL（V1.0.0，MySQL 5.7+/8.0 / InnoDB / utf8mb4）
-- 来源：asterism-docs/20-design/P6-详细设计/bc-model/逻辑数据模型.md
-- 落点约定：<repo>/db/migration/mysql/V1.0.0__model.sql（参照 Nebula Flyway 版本控制）
-- 默认数据库方言（用户指定统一默认 MySQL）；SQLite 仅用于零依赖测试。
-- 硬约束（DDD 战术设计）：
--   1) 1 聚合 = 1 主表（vendors / prompt_templates 为聚合根主表）
--   2) 聚合根主表含 version 乐观锁（BIGINT，冲突映射 409）
--   3) 跨聚合只存 ID；models.vendor_id 为聚合内关联（同一 BC，非跨 BC 外键）
--   4) tenant_id 行级隔离 + 索引（FIELD 租户隔离模式）
--   5) 凭据句柄 credential_handle 仅密文定位引用（L3 不落明文）
-- 类型约定（MySQL 方言）：JSON→JSON；BOOLEAN→TINYINT(1)；乐观锁 version→BIGINT
-- 注：本脚本已联调验证（环境 MySQL 5.7.44，凭据 nebula/nebula，2026-10-11）：vendors/models/prompt_templates 三表 + schema_version 建表通过，BC-MODEL 集成测试 4 例全绿（见 tests/integration/model/test_model_persistence.py）。兼容 MySQL 5.7+/8.0。
-- 幂等：全部 IF NOT EXISTS；重放安全（apply_migrations 按 schema_version 去重）
-- =====================================================================

SET NAMES utf8mb4;

-- 2.1 厂商聚合根主表（ET-03 演进：Vendor 聚合根 = 身份 + VendorConfig(VO) + models）
CREATE TABLE IF NOT EXISTS vendors (
    vendor_id               VARCHAR(64)  NOT NULL                COMMENT 'Vendor 聚合根 ID',
    plugin_registration_ref VARCHAR(255) NOT NULL                COMMENT '插件注册项引用（1:1，IN1）',
    name                   VARCHAR(128) NOT NULL                COMMENT '厂商名称',
    status                 VARCHAR(32)  NOT NULL DEFAULT '停用'  COMMENT '启用/停用',
    tenant_id              VARCHAR(64)  NOT NULL                COMMENT '租户隔离维度（字段级）',
    version                BIGINT       NOT NULL DEFAULT 1      COMMENT '乐观锁（冲突 409）',
    access_protocol        VARCHAR(64)  NOT NULL                COMMENT '访问协议（openai/anthropic/...）',
    base_url               TEXT         NOT NULL                COMMENT '基址 URL',
    credential_handle      VARCHAR(512) NOT NULL                COMMENT 'L3 凭据句柄（仅密文定位引用）',
    default_timeout_budget_ms BIGINT    NOT NULL                COMMENT '默认超时预算(ms)',
    failover_target_ref    VARCHAR(255) DEFAULT NULL             COMMENT '回退目标引用（聚合内/跨 BC 仅 ID）',
    PRIMARY KEY (vendor_id),
    UNIQUE KEY uk_plugin_registration_ref (plugin_registration_ref)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COMMENT = '厂商聚合根主表（ET-03 演进）';
CREATE INDEX idx_vendors_tenant ON vendors (tenant_id);
CREATE INDEX idx_vendors_status ON vendors (status);

-- 2.2 模型（聚合内实体，从属于 Vendor；vendor_id 聚合内关联）
CREATE TABLE IF NOT EXISTS models (
    model_id               VARCHAR(64)  NOT NULL                COMMENT 'Model 聚合内实体 ID',
    vendor_id              VARCHAR(64)  NOT NULL                COMMENT '所属 Vendor（聚合内关联）',
    tenant_id              VARCHAR(64)  NOT NULL                COMMENT '租户隔离维度',
    name                   VARCHAR(128) NOT NULL                COMMENT '模型名称',
    capability_context_window BIGINT    NOT NULL                COMMENT '上下文窗口(token)',
    capability_modalities  JSON         NOT NULL                COMMENT '模态列表 JSON',
    capability_pricing     VARCHAR(512) NOT NULL DEFAULT ''      COMMENT '计价说明',
    is_default             TINYINT(1)   NOT NULL DEFAULT 0       COMMENT '是否默认模型(0/1)',
    prompt_template_ids    JSON         NOT NULL                COMMENT '关联提示词模板 ID 列表 JSON',
    PRIMARY KEY (model_id),
    CONSTRAINT fk_models_vendor FOREIGN KEY (vendor_id) REFERENCES vendors (vendor_id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COMMENT = '模型（聚合内实体）';
CREATE INDEX idx_models_vendor ON models (vendor_id);
CREATE INDEX idx_models_tenant ON models (tenant_id);

-- 2.3 提示词模板（独立聚合根，可跨 Model / 跨 BC 复用，需稳定 ID 引用）
CREATE TABLE IF NOT EXISTS prompt_templates (
    template_id            VARCHAR(64)  NOT NULL                COMMENT 'PromptTemplate 聚合根 ID',
    name                   VARCHAR(128) NOT NULL                COMMENT '模板名称',
    content                TEXT         NOT NULL                COMMENT '模板内容（含 {{var}} 占位符）',
    variables              JSON         NOT NULL                COMMENT '变量声明 JSON',
    version                BIGINT       NOT NULL DEFAULT 1      COMMENT '乐观锁',
    model_affinity         VARCHAR(64)  DEFAULT NULL             COMMENT '模型亲和（可选）',
    status                 VARCHAR(32)  NOT NULL DEFAULT '启用'  COMMENT '草稿/启用/停用',
    tenant_id              VARCHAR(64)  NOT NULL                COMMENT '租户隔离维度',
    PRIMARY KEY (template_id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COMMENT = '提示词模板（独立聚合根）';
CREATE INDEX idx_prompt_templates_tenant ON prompt_templates (tenant_id);
CREATE INDEX idx_prompt_templates_name ON prompt_templates (name);
