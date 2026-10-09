"""系统管理接口层 Schema（Pydantic v2）。"""

from __future__ import annotations

from typing import List

from pydantic import BaseModel


class UserOut(BaseModel):
    id: str
    tenant_id: str
    name: str
    roles: List[str] = []


class RoleOut(BaseModel):
    id: str
    tenant_id: str
    name: str
    permissions: List[str] = []


class MenuOut(BaseModel):
    id: str
    tenant_id: str
    title: str
    path: str
