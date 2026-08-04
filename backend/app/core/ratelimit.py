"""登录失败计数与锁定：优先使用 Redis，Redis 不可用时降级为进程内内存计数。"""
import time

from app.core.config import settings

try:  # redis 已在依赖中，但连接可能不可用（如 SQLite 单机开发）
    import redis.asyncio as aioredis
except Exception:  # noqa: BLE001
    aioredis = None  # type: ignore[assignment]

_redis = None
# 进程内降级存储：key -> (count, window_start_ts)
_mem: dict[str, tuple[int, float]] = {}


async def _get_redis():
    global _redis
    if aioredis is None:
        return None
    if _redis is None:
        _redis = aioredis.from_url(settings.REDIS_URL, encoding="utf-8", decode_responses=True)
    return _redis


async def get_failures(key: str, window: int) -> int:
    try:
        r = await _get_redis()
        if r is not None:
            return int(await r.get(key) or 0)
    except Exception:  # noqa: BLE001  Redis 不可用则降级
        pass
    now = time.time()
    cnt, ts = _mem.get(key, (0, now))
    if now - ts > window:
        return 0
    return cnt


async def incr_failure(key: str, window: int) -> None:
    try:
        r = await _get_redis()
        if r is not None:
            n = await r.incr(key)
            if n == 1:
                await r.expire(key, window)
            return
    except Exception:  # noqa: BLE001
        pass
    now = time.time()
    cnt, ts = _mem.get(key, (0, now))
    if now - ts > window:
        cnt, ts = 0, now
    _mem[key] = (cnt + 1, ts)


async def clear_failures(key: str) -> None:
    try:
        r = await _get_redis()
        if r is not None:
            await r.delete(key)
    except Exception:  # noqa: BLE001
        pass
    _mem.pop(key, None)
