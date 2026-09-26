"""后台任务幂等键（P0-2）：抢占 / 释放 / 清理。

队列语义是「至少一次」（arq 失败重试、进程重启后的恢复投递），因此任务本身必须幂等。
本模块提供数据库级的幂等键占位：

- `claim_dedup_key(key)`：`INSERT ... ON CONFLICT DO NOTHING`，抢占成功说明这是首次执行；
  抢占失败说明同一业务副作用已经（或正在）执行，调用方应直接返回，不产生第二次副作用。
- `release_dedup_key(key)`：执行失败时释放，让重试仍然可用（否则一次网络抖动会让通知永久丢失）。
- `cleanup_dedup_keys()`：删除超过保留期的键，避免无界增长（由 worker 定期任务调用）。
"""
from datetime import timedelta

from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutil import now
from app.models import TaskDedupKey

# 幂等键保留期：覆盖队列最长重试窗口（arq job_timeout 600s + 多次重试）后即可回收
DEDUP_TTL_DAYS = 7


async def claim_dedup_key(session: AsyncSession, key: str) -> bool:
    """抢占幂等键：首次执行返回 True；已被占用返回 False。"""
    result = await session.execute(
        pg_insert(TaskDedupKey)
        .values(key=key)
        .on_conflict_do_nothing(index_elements=[TaskDedupKey.key])
    )
    return result.rowcount == 1


async def release_dedup_key(session: AsyncSession, key: str) -> None:
    """释放幂等键（执行失败时调用），使重试仍可执行。"""
    await session.execute(delete(TaskDedupKey).where(TaskDedupKey.key == key))


async def cleanup_dedup_keys(session: AsyncSession, ttl_days: int = DEDUP_TTL_DAYS) -> int:
    """删除保留期之外的幂等键，返回删除条数。"""
    result = await session.execute(
        delete(TaskDedupKey).where(TaskDedupKey.create_time < now() - timedelta(days=ttl_days))
    )
    return int(result.rowcount or 0)
