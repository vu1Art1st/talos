"""时间辅助：统一 UTC 取值，替代已弃用的 datetime.utcnow()。

返回 naive（无时区）UTC 时间，与数据库中 DateTime（Postgres TIMESTAMP WITHOUT
TIME ZONE）列保持一致——asyncpg 会拒绝把带时区的 datetime 写入无时区列，故此处
统一去除 tzinfo，既消除 utcnow() 的弃用告警，又避免 naive/aware 混用引发的错误。
"""
from datetime import datetime, timezone


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)
