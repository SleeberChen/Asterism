"""缓存键构造器单元测试（TC-13：键强制含 tenant_id）。"""

from __future__ import annotations

import pytest

from asterism.infrastructure.cache import build_cache_key
from asterism.seedwork.exceptions import BusinessError


def test_key_prefix_includes_tenant():
    key = build_cache_key("rag", "retrieve", "abc", tenant_id="t1")
    assert key.startswith("ck:t1:")


def test_missing_tenant_rejected():
    with pytest.raises(BusinessError):
        build_cache_key("rag", tenant_id="")
