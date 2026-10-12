"""BC-MODEL 持久化层（SQLAlchemy 2.x）。

DB 实现替换原内存仓储；仓储对外方法签名保持不变（DMP-13 聚合=事务边界，本地强一致）。
生产可经 DATABASE_URL 切换 PostgreSQL，无需改仓储代码。
"""
