"""缓存抽象与进程内实现（P5 P4 第 10 章 C01~C07）。

本期只落地进程内实现（无专职运维，不引入分布式缓存）。
缓存键构造器强制含 ``tenant_id``（TC-13：不含隔离维度的键数 = 0）。
"""

from .cache_key import build_cache_key
from .memory_cache import MemoryCache

__all__ = ["build_cache_key", "MemoryCache"]
