"""时间辅助：统一按系统标准时区（默认 UTC+8 北京时间）取值。

返回 naive（无时区）本地时间，与数据库中 DateTime（Postgres TIMESTAMP WITHOUT
TIME ZONE）列保持一致——asyncpg 会拒绝把带时区的 datetime 写入无时区列，故此处
统一去除 tzinfo，既消除 datetime.utcnow() 的弃用告警，又避免 naive/aware 混用
引发的错误。

系统时区可通过环境变量 VP_TIMEZONE 覆盖（IETF 时区名，如 Asia/Shanghai），
默认 UTC+8 北京时间。zoneinfo 需要系统时区库或 tzdata 包（Windows 上为后者，
已在 requirements.txt 引入）；解析失败时兜底使用固定 UTC+8 偏移。旧版本以 UTC
存储的存量数据需执行 scripts/migrate_utc_to_utc8.py 一次性 +8h 换算。
"""
from datetime import datetime, timedelta, timezone, tzinfo
from functools import lru_cache
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.core.config import settings

# 固定 UTC+8 偏移：作为 ZoneInfo 解析失败的兜底（如未安装 tzdata 的 Windows 环境）
_UTC8 = timezone(timedelta(hours=8))


@lru_cache(maxsize=1)
def _system_tz() -> tzinfo:
    try:
        return ZoneInfo(settings.TIMEZONE)
    except (ZoneInfoNotFoundError, ValueError, OSError):
        return _UTC8


def now() -> datetime:
    """当前系统时间（默认 UTC+8）的 naive 本地时间，业务写入与展示统一使用。"""
    return datetime.now(_system_tz()).replace(tzinfo=None)


def utcnow() -> datetime:
    """当前 UTC 时间（naive），用于 JWT 等绝对时间戳，区别于业务本地时间。"""
    return datetime.now(timezone.utc).replace(tzinfo=None)
