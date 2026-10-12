"""BC-MODEL 仓储契约 + 内存实现（演示/测试用；生产替换为 DB 实现，接口不变）。

全链路异步：所有方法为协程（``async def``）；内存实现直接返回，但满足同一异步契约，
便于 ``SqlVendorRepository`` 无缝替换（依赖倒置 TC-09）。

tenant_id 行级隔离；version 乐观锁（冲突抛 ``ConcurrencyError`` 映射 409）。
get_by_id 返回副本，避免调用方原地修改穿透到已提交实例；save 时比对基线版本，
一致则提交并将版本 +1，不一致则冲突（DMP-13 聚合 = 事务边界，本地强一致）。
"""

from __future__ import annotations

import dataclasses
from typing import Optional

from .catalog import Vendor, PromptTemplate, Model, NotFoundError, ConcurrencyError


class VendorRepository:
    def __init__(self) -> None:
        self._by_id: dict[tuple[str, str], Vendor] = {}  # (tenant, vendor_id)
        self._by_plugin: dict[tuple[str, str], str] = {}  # (tenant, plugin_ref) -> vendor_id

    # --- 查询（返回副本，隔离已提交实例） ---
    async def get_by_id(self, vendor_id: str, tenant_id: str) -> Vendor:
        v = self._by_id.get((tenant_id, vendor_id))
        if v is None:
            raise NotFoundError(f"厂商不存在: {vendor_id}")
        return dataclasses.replace(v, models=list(v.models))

    async def get_by_plugin_ref(self, plugin_ref: str, tenant_id: str) -> Optional[Vendor]:
        vid = self._by_plugin.get((tenant_id, plugin_ref))
        return await self.get_by_id(vid, tenant_id) if vid else None

    async def list_by_name(self, name: str, tenant_id: str) -> list[Vendor]:
        return [v for v in self._by_id.values() if v.tenant_id == tenant_id and v.name == name]

    async def list_by_status(self, status: str, tenant_id: str) -> list[Vendor]:
        return [v for v in self._by_id.values() if v.tenant_id == tenant_id and v.status == status]

    async def scan(self, tenant_id: str) -> list[Vendor]:
        return [v for v in self._by_id.values() if v.tenant_id == tenant_id]

    # --- 写（乐观锁） ---
    async def save(self, vendor: Vendor) -> str:
        key = (vendor.tenant_id, vendor.vendor_id)
        existing = self._by_id.get(key)
        if existing is None:
            self._by_id[key] = vendor
            self._by_plugin[(vendor.tenant_id, vendor.plugin_registration_ref)] = vendor.vendor_id
            return vendor.vendor_id
        if existing.version != vendor.version:
            raise ConcurrencyError("数据已被他人修改，请刷新后重试（409）")
        vendor.version += 1
        self._by_id[key] = vendor
        return vendor.vendor_id

    async def set_status(self, vendor_id: str, status: str, expected_version: int, tenant_id: str) -> None:
        v = await self.get_by_id(vendor_id, tenant_id)
        if v.version != expected_version:
            raise ConcurrencyError("数据已被他人修改，请刷新后重试（409）")
        v.status = status
        await self.save(v)

    async def replace_credential_handle(
        self, vendor_id: str, new_handle: str, expected_version: int, tenant_id: str
    ) -> None:
        v = await self.get_by_id(vendor_id, tenant_id)
        if v.version != expected_version:
            raise ConcurrencyError("数据已被他人修改，请刷新后重试（409）")
        v.rotate_credentials(new_handle)
        await self.save(v)

    # --- 聚合内模型 ---
    async def list_models(self, vendor_id: str, tenant_id: str) -> list[Model]:
        return list((await self.get_by_id(vendor_id, tenant_id)).models)

    async def get_default_model(self, vendor_id: str, tenant_id: str) -> Optional[Model]:
        for m in (await self.get_by_id(vendor_id, tenant_id)).models:
            if m.is_default:
                return m
        return None


class PromptTemplateRepository:
    def __init__(self) -> None:
        self._by_id: dict[tuple[str, str], PromptTemplate] = {}

    async def get_by_id(self, template_id: str, tenant_id: str) -> PromptTemplate:
        t = self._by_id.get((tenant_id, template_id))
        if t is None:
            raise NotFoundError(f"提示词模板不存在: {template_id}")
        return dataclasses.replace(t, variables=list(t.variables))

    async def list_by_name(self, name: str, tenant_id: str) -> list[PromptTemplate]:
        return [t for t in self._by_id.values() if t.tenant_id == tenant_id and t.name == name]

    async def save(self, tmpl: PromptTemplate) -> str:
        key = (tmpl.tenant_id, tmpl.template_id)
        existing = self._by_id.get(key)
        if existing is None:
            self._by_id[key] = tmpl
            return tmpl.template_id
        if existing.version != tmpl.version:
            raise ConcurrencyError("数据已被他人修改，请刷新后重试（409）")
        tmpl.version += 1
        self._by_id[key] = tmpl
        return tmpl.template_id

    async def publish(self, template_id: str, tenant_id: str) -> PromptTemplate:
        t = await self.get_by_id(template_id, tenant_id)
        t.status = "启用"
        await self.save(t)
        return t
