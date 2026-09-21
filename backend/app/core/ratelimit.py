"""登录失败计数与锁定：优先使用 Redis，Redis 不可用时降级为进程内内存计数。"""
import time

from app.core.config import settings

try:  # redis 已在依赖中，但连接可能不可用（如本地未启用 Redis 的单机运行）
    import redis.asyncio as aioredis
except Exception:  # noqa: BLE001
    aioredis = None  # type: ignore[assignment]

_redis = None
# 进程内降级存储：key -> (count, window_start_ts)
_mem: dict[str, tuple[int, float]] = {}


async def _get_redis():
    global _redis
    # DISABLE_REDIS：明确不使用 Redis（测试 / 无 Redis 的单机环境）→ 直接走进程内降级。
    # G7 的超时保证"不可达时有界"，本开关让"已知无 Redis"的场景零成本（不再逐次尝试连接）
    if aioredis is None or settings.DISABLE_REDIS:
        return None
    if _redis is None:
        # 必须显式设置连接/读写超时：Redis 不可达但对端 DROP 报文（而非主动拒绝）时，
        # 无超时的客户端会停在 TCP 握手阶段无限挂起，下方 except 的降级分支将永不触发（G7）
        _redis = aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
            socket_connect_timeout=settings.REDIS_TIMEOUT,
            socket_timeout=settings.REDIS_TIMEOUT,
        )
    return _redis


async def get_shared_redis():
    """供其它模块复用同一 Redis 客户端（连接池/超时口径唯一，见 tests/test_ratelimit_timeout.py 的 G7 守卫）。

    Redis 不可用时返回 None，调用方须自行降级（refresh token 轮换状态见 core/token_store.py）。
    """
    return await _get_redis()


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
