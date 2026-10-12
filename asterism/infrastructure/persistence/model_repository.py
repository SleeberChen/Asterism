"""BC-MODEL SQL 异步仓储（接口与 ``domain/model/repository.py`` 内存版一致；全链路协程）。

行模型：``vendors``（聚合根 ET-03，单表）/ ``models``（聚合内实体，vendor_id 关联）/
``prompt_templates``（独立聚合根，新 ET-0x 待登记）。
tenant_id 行级隔离；version 乐观锁（冲突抛 ConcurrencyError 映射 409）。
会话为 AsyncSession，所有方法为协程（需 running loop）。
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy import Boolean, ForeignKey, Integer, JSON, String, Text, delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base
from ...domain.model.catalog import (
    Vendor,
    VendorConfig,
    Model,
    ModelCapability,
    PromptTemplate,
    PromptVariable,
    NotFoundError,
    ConcurrencyError,
)
from ...domain.model.repository import VendorRepository, PromptTemplateRepository


# ---------------------------------------------------------------------------
# 行模型
# ---------------------------------------------------------------------------
class VendorRow(Base):
    __tablename__ = "asterism_vendors"

    vendor_id: Mapped[str] = mapped_column(String, primary_key=True)
    plugin_registration_ref: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="停用")
    tenant_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    # VendorConfig（VO，扁平存储）
    access_protocol: Mapped[str] = mapped_column(String, nullable=False)
    base_url: Mapped[str] = mapped_column(String, nullable=False)
    credential_handle: Mapped[str] = mapped_column(String, nullable=False)  # L3：仅密文定位引用
    default_timeout_budget_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    failover_target_ref: Mapped[Optional[str]] = mapped_column(String, nullable=True)


class ModelRow(Base):
    __tablename__ = "asterism_models"

    model_id: Mapped[str] = mapped_column(String, primary_key=True)
    vendor_id: Mapped[str] = mapped_column(
        String, ForeignKey("asterism_vendors.vendor_id"), nullable=False, index=True
    )  # 聚合内关联（同一 BC/DA-03，非跨聚合外键）
    tenant_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    capability_context_window: Mapped[int] = mapped_column(Integer, nullable=False)
    capability_modalities: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    capability_pricing: Mapped[str] = mapped_column(String, nullable=False, default="")
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    prompt_template_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)


class PromptTemplateRow(Base):
    __tablename__ = "asterism_prompt_templates"

    template_id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    variables: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    model_affinity: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="启用")
    tenant_id: Mapped[str] = mapped_column(String, nullable=False, index=True)


# ---------------------------------------------------------------------------
# 映射
# ---------------------------------------------------------------------------
def _vendor_row(v: Vendor) -> VendorRow:
    return VendorRow(
        vendor_id=v.vendor_id,
        plugin_registration_ref=v.plugin_registration_ref,
        name=v.name,
        status=v.status,
        tenant_id=v.tenant_id,
        version=v.version,
        access_protocol=v.config.access_protocol,
        base_url=v.config.base_url,
        credential_handle=v.config.credential_handle,
        default_timeout_budget_ms=v.config.default_timeout_budget_ms,
        failover_target_ref=v.failover_target_ref,
    )


async def _vendor_to_domain(row: VendorRow, session: AsyncSession) -> Vendor:
    res = await session.execute(select(ModelRow).filter_by(vendor_id=row.vendor_id))
    models = res.scalars().all()
    return Vendor(
        vendor_id=row.vendor_id,
        plugin_registration_ref=row.plugin_registration_ref,
        name=row.name,
        config=VendorConfig(
            access_protocol=row.access_protocol,
            base_url=row.base_url,
            credential_handle=row.credential_handle,
            default_timeout_budget_ms=row.default_timeout_budget_ms,
        ),
        status=row.status,
        tenant_id=row.tenant_id,
        version=row.version,
        models=[_model_to_domain(m) for m in models],
        failover_target_ref=row.failover_target_ref,
    )


def _model_row(vendor_id: str, tenant_id: str, m: Model) -> ModelRow:
    return ModelRow(
        model_id=m.model_id,
        vendor_id=vendor_id,
        tenant_id=tenant_id,
        name=m.name,
        capability_context_window=m.capability.context_window,
        capability_modalities=list(m.capability.modalities),
        capability_pricing=m.capability.pricing_note,
        is_default=m.is_default,
        prompt_template_ids=list(m.prompt_template_ids),
    )


def _model_to_domain(r: ModelRow) -> Model:
    return Model(
        model_id=r.model_id,
        name=r.name,
        capability=ModelCapability(
            context_window=r.capability_context_window,
            modalities=tuple(r.capability_modalities or ()),
            pricing_note=r.capability_pricing or "",
        ),
        is_default=r.is_default,
        prompt_template_ids=list(r.prompt_template_ids or []),
    )


def _template_row(t: PromptTemplate) -> PromptTemplateRow:
    return PromptTemplateRow(
        template_id=t.template_id,
        name=t.name,
        content=t.content,
        variables=[{"name": v.name, "type": v.type, "default": v.default} for v in t.variables],
        version=t.version,
        model_affinity=t.model_affinity,
        status=t.status,
        tenant_id=t.tenant_id,
    )


def _template_to_domain(row: PromptTemplateRow) -> PromptTemplate:
    return PromptTemplate(
        template_id=row.template_id,
        name=row.name,
        content=row.content,
        variables=[PromptVariable(**v) for v in (row.variables or [])],
        version=row.version,
        model_affinity=row.model_affinity,
        status=row.status,
        tenant_id=row.tenant_id,
    )


# ---------------------------------------------------------------------------
# SQL 异步仓储（接口与内存版一致）
# ---------------------------------------------------------------------------
class SqlVendorRepository(VendorRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def get_by_id(self, vendor_id: str, tenant_id: str) -> Vendor:
        row = await self._s.get(VendorRow, vendor_id)
        if row is None or row.tenant_id != tenant_id:
            raise NotFoundError(f"厂商不存在: {vendor_id}")
        return await _vendor_to_domain(row, self._s)

    async def get_by_plugin_ref(self, plugin_ref: str, tenant_id: str) -> Optional[Vendor]:
        res = await self._s.execute(
            select(VendorRow).filter_by(plugin_registration_ref=plugin_ref, tenant_id=tenant_id)
        )
        row = res.scalars().first()
        return await _vendor_to_domain(row, self._s) if row else None

    async def list_by_name(self, name: str, tenant_id: str) -> list[Vendor]:
        res = await self._s.execute(select(VendorRow).filter_by(name=name, tenant_id=tenant_id))
        return [await _vendor_to_domain(r, self._s) for r in res.scalars().all()]

    async def list_by_status(self, status: str, tenant_id: str) -> list[Vendor]:
        res = await self._s.execute(select(VendorRow).filter_by(status=status, tenant_id=tenant_id))
        return [await _vendor_to_domain(r, self._s) for r in res.scalars().all()]

    async def scan(self, tenant_id: str) -> list[Vendor]:
        res = await self._s.execute(select(VendorRow).filter_by(tenant_id=tenant_id))
        return [await _vendor_to_domain(r, self._s) for r in res.scalars().all()]

    async def save(self, vendor: Vendor) -> str:
        existing = await self._s.get(VendorRow, vendor.vendor_id)
        if existing is None:
            self._s.add(_vendor_row(vendor))
            for m in vendor.models:
                self._s.add(_model_row(vendor.vendor_id, vendor.tenant_id, m))
            await self._s.commit()
            return vendor.vendor_id
        if existing.version != vendor.version:
            raise ConcurrencyError("数据已被他人修改，请刷新后重试（409）")
        existing.name = vendor.name
        existing.status = vendor.status
        existing.version = vendor.version + 1
        existing.access_protocol = vendor.config.access_protocol
        existing.base_url = vendor.config.base_url
        existing.credential_handle = vendor.config.credential_handle
        existing.default_timeout_budget_ms = vendor.config.default_timeout_budget_ms
        existing.failover_target_ref = vendor.failover_target_ref
        # 聚合内模型整体替换（本地事务强一致）
        await self._s.execute(delete(ModelRow).where(ModelRow.vendor_id == vendor.vendor_id))
        for m in vendor.models:
            self._s.add(_model_row(vendor.vendor_id, vendor.tenant_id, m))
        await self._s.commit()
        # 与内存仓储契约一致：写后回填调用方聚合根的版本，使同一内存对象可再次安全 save
        vendor.version = existing.version
        return vendor.vendor_id

    async def set_status(self, vendor_id: str, status: str, expected_version: int, tenant_id: str) -> None:
        row = await self._s.get(VendorRow, vendor_id)
        if row is None or row.tenant_id != tenant_id:
            raise NotFoundError(f"厂商不存在: {vendor_id}")
        if row.version != expected_version:
            raise ConcurrencyError("数据已被他人修改，请刷新后重试（409）")
        row.status = status
        row.version = expected_version + 1
        await self._s.commit()

    async def replace_credential_handle(
        self, vendor_id: str, new_handle: str, expected_version: int, tenant_id: str
    ) -> None:
        row = await self._s.get(VendorRow, vendor_id)
        if row is None or row.tenant_id != tenant_id:
            raise NotFoundError(f"厂商不存在: {vendor_id}")
        if row.version != expected_version:
            raise ConcurrencyError("数据已被他人修改，请刷新后重试（409）")
        row.credential_handle = new_handle
        row.version = expected_version + 1
        await self._s.commit()

    async def replace_connection_config(
        self,
        vendor_id: str,
        access_protocol: str,
        base_url: str,
        default_timeout_budget_ms: int,
        expected_version: int,
        tenant_id: str,
    ) -> None:
        row = await self._s.get(VendorRow, vendor_id)
        if row is None or row.tenant_id != tenant_id:
            raise NotFoundError(f"厂商不存在: {vendor_id}")
        if row.version != expected_version:
            raise ConcurrencyError("数据已被他人修改，请刷新后重试（409）")
        row.access_protocol = access_protocol
        row.base_url = base_url
        row.default_timeout_budget_ms = default_timeout_budget_ms
        row.version = expected_version + 1
        await self._s.commit()

    async def list_models(self, vendor_id: str, tenant_id: str) -> list[Model]:
        res = await self._s.execute(
            select(ModelRow).filter_by(vendor_id=vendor_id, tenant_id=tenant_id)
        )
        return [_model_to_domain(r) for r in res.scalars().all()]

    async def get_default_model(self, vendor_id: str, tenant_id: str) -> Optional[Model]:
        res = await self._s.execute(
            select(ModelRow).filter_by(vendor_id=vendor_id, tenant_id=tenant_id, is_default=True)
        )
        row = res.scalars().first()
        return _model_to_domain(row) if row else None

    async def scan_models(self, tenant_id: str) -> list[tuple[str, Model]]:
        """跨厂商列出本租户全部模型，返回 (vendor_id, Model)。"""
        res = await self._s.execute(select(ModelRow).filter_by(tenant_id=tenant_id))
        return [(r.vendor_id, _model_to_domain(r)) for r in res.scalars().all()]

    async def get_model(self, model_id: str, tenant_id: str) -> Optional[tuple[str, Model]]:
        """跨厂商按 id 查模型，命中返回 (vendor_id, Model)，否则 None。"""
        res = await self._s.execute(
            select(ModelRow).filter_by(model_id=model_id, tenant_id=tenant_id)
        )
        row = res.scalars().first()
        return (row.vendor_id, _model_to_domain(row)) if row else None

    # --- 删除（行级隔离；校验租户；聚合内模型先清，再删聚合根，规避 FK RESTRICT） ---
    async def delete(self, vendor_id: str, tenant_id: str) -> None:
        row = await self._s.get(VendorRow, vendor_id)
        if row is None or row.tenant_id != tenant_id:
            raise NotFoundError(f"厂商不存在: {vendor_id}")
        await self._s.execute(
            delete(ModelRow).where(ModelRow.vendor_id == vendor_id, ModelRow.tenant_id == tenant_id)
        )
        await self._s.execute(
            delete(VendorRow).where(VendorRow.vendor_id == vendor_id, VendorRow.tenant_id == tenant_id)
        )
        await self._s.commit()

    async def delete_model(self, vendor_id: str, model_id: str, tenant_id: str) -> None:
        row = await self._s.get(ModelRow, model_id)
        if row is None or row.tenant_id != tenant_id or row.vendor_id != vendor_id:
            raise NotFoundError(f"模型不存在: {model_id}")
        await self._s.execute(delete(ModelRow).where(ModelRow.model_id == model_id))
        await self._s.commit()


class SqlPromptTemplateRepository(PromptTemplateRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def get_by_id(self, template_id: str, tenant_id: str) -> PromptTemplate:
        row = await self._s.get(PromptTemplateRow, template_id)
        if row is None or row.tenant_id != tenant_id:
            raise NotFoundError(f"提示词模板不存在: {template_id}")
        return _template_to_domain(row)

    async def list_by_name(self, name: str, tenant_id: str) -> list[PromptTemplate]:
        res = await self._s.execute(
            select(PromptTemplateRow).filter_by(name=name, tenant_id=tenant_id)
        )
        return [_template_to_domain(r) for r in res.scalars().all()]

    async def save(self, tmpl: PromptTemplate) -> str:
        existing = await self._s.get(PromptTemplateRow, tmpl.template_id)
        if existing is None:
            self._s.add(_template_row(tmpl))
            await self._s.commit()
            return tmpl.template_id
        if existing.version != tmpl.version:
            raise ConcurrencyError("数据已被他人修改，请刷新后重试（409）")
        existing.name = tmpl.name
        existing.content = tmpl.content
        existing.variables = [
            {"name": v.name, "type": v.type, "default": v.default} for v in tmpl.variables
        ]
        existing.version = tmpl.version + 1
        existing.model_affinity = tmpl.model_affinity
        existing.status = tmpl.status
        existing.tenant_id = tmpl.tenant_id
        await self._s.commit()
        # 与内存仓储契约一致：写后回填调用方聚合根的版本，使同一内存对象可再次安全 save
        tmpl.version = existing.version
        return tmpl.template_id

    async def publish(self, template_id: str, tenant_id: str) -> PromptTemplate:
        row = await self._s.get(PromptTemplateRow, template_id)
        if row is None or row.tenant_id != tenant_id:
            raise NotFoundError(f"提示词模板不存在: {template_id}")
        row.status = "启用"
        row.version = row.version + 1
        await self._s.commit()
        return _template_to_domain(row)


def build_model_repositories(session: AsyncSession) -> tuple[SqlVendorRepository, SqlPromptTemplateRepository]:
    """构造共享同一异步会话的模型仓储（组合根使用）。"""
    return SqlVendorRepository(session), SqlPromptTemplateRepository(session)
