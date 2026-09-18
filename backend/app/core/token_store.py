"""refresh token 轮换状态：jti 一次性 + 宽限期（安全审计 批次 E-3）。

背景：原 `/auth/refresh` 只校验签名与 `token_version`，同一个 refresh token 在 24h 窗口内
可被无限次重复兑换——令牌一旦泄露，攻击者可长期维持会话，且合法用户重新登录也不会让
泄露的令牌失效。本模块为每个用户维护：

- `refresh:{uid}`      → **活跃 jti 列表**（JSON，上限 `_MAX_SESSIONS`，TTL = refresh 生命周期）
- `refresh_prev:{uid}` → 最近被轮换掉的 jti 列表（JSON，TTL = 宽限期）

语义（见 `api/v1/auth.py`）：
- 登录：把新 jti 追加进活跃列表（多设备并存，上限 5；超出淘汰最旧一条）；
- 刷新：jti ∈ 活跃列表 → 轮换（旧 jti 移入宽限列表）；jti ∈ 宽限列表 → 允许再轮换一次
  （多标签页/并发刷新的正常现象，窗口见 `config.REFRESH_GRACE_SECONDS`）；其余 → 401；
- 退出：把该 jti 移出活跃列表；改密/禁用：清空全部（所有设备重新登录）。

为什么不需要「每用户仅一个 refresh token」：那会让第二台设备登录后把第一台挤下线；
按 jti 维持小规模活跃集合即可兼顾轮换强度与多端体验。

存储：Redis 优先（多进程/重启后仍有效），不可用时降级为进程内内存（单机/测试）；
刻意复用 `core/ratelimit.get_shared_redis()`，连接与超时口径唯一（G7 守卫）。
"""
import json
import time

from app.core.ratelimit import get_shared_redis

# 单用户同时活跃的 refresh token 数上限（多设备）
_MAX_SESSIONS = 5

# 进程内降级存储：key -> (value_json, expire_ts)
_mem: dict[str, tuple[str, float]] = {}

_ACTIVE = "refresh:{uid}"
_PREV = "refresh_prev:{uid}"


async def _get(key: str) -> str:
    try:
        r = await get_shared_redis()
        if r is not None:
            return await r.get(key) or ""
    except Exception:  # noqa: BLE001  Redis 不可用则降级
        pass
    value, expire = _mem.get(key, ("", 0.0))
    if expire and time.time() > expire:
        _mem.pop(key, None)
        return ""
    return value


async def _set(key: str, value: str, ttl: int) -> None:
    try:
        r = await get_shared_redis()
        if r is not None:
            await r.set(key, value, ex=ttl)
            return
    except Exception:  # noqa: BLE001
        pass
    _mem[key] = (value, time.time() + ttl)


async def _delete(key: str) -> None:
    try:
        r = await get_shared_redis()
        if r is not None:
            await r.delete(key)
    except Exception:  # noqa: BLE001
        pass
    _mem.pop(key, None)


def _load(raw: str) -> list[str]:
    if not raw:
        return []
    try:
        values = json.loads(raw)
    except ValueError:
        return []
    return [v for v in values if isinstance(v, str)] if isinstance(values, list) else []


async def _active(uid: int) -> list[str]:
    return _load(await _get(_ACTIVE.format(uid=uid)))


async def _prev(uid: int) -> list[str]:
    return _load(await _get(_PREV.format(uid=uid)))


async def add_session(uid: int, jti: str, ttl: int) -> None:
    """登录成功后登记新会话（多设备并存，超出上限淘汰最旧）。"""
    sessions = [j for j in await _active(uid) if j != jti]
    sessions = [*sessions, jti][-_MAX_SESSIONS:]
    await _set(_ACTIVE.format(uid=uid), json.dumps(sessions), ttl)


async def is_acceptable(uid: int, jti: str) -> bool:
    """该 jti 是否可用于兑换：在活跃列表内，或位于宽限列表内（刚被轮换掉的）。

    空 jti（本次升级前签发的老令牌）放行一次：轮换后即带 jti 纳入新机制，避免升级即全员掉线。
    """
    if not jti:
        return True
    return jti in await _active(uid) or jti in await _prev(uid)


async def rotate(uid: int, old_jti: str, new_jti: str, ttl: int, grace: int) -> None:
    """轮换：新 jti 进入活跃列表，旧 jti 移入宽限列表（保留最近 2 个）。"""
    sessions = [j for j in await _active(uid) if j != old_jti and j != new_jti]
    await _set(_ACTIVE.format(uid=uid), json.dumps([*sessions, new_jti][-_MAX_SESSIONS:]), ttl)
    if not old_jti:
        return
    prev = [j for j in await _prev(uid) if j != old_jti]
    await _set(_PREV.format(uid=uid), json.dumps([old_jti, *prev][:2]), grace)


async def end_session(uid: int, jti: str) -> None:
    """退出登录：仅注销该会话（其它设备不受影响）。jti 缺失时按 uid 全量清理。"""
    if not jti:
        await end_all(uid)
        return
    sessions = [j for j in await _active(uid) if j != jti]
    await _set(_ACTIVE.format(uid=uid), json.dumps(sessions), 60 * 60 * 24 * 30)
    await _delete(_PREV.format(uid=uid))


async def end_all(uid: int) -> None:
    """改密/禁用等场景：清空该用户全部轮换状态（所有设备的 refresh token 立即失效）。"""
    await _delete(_ACTIVE.format(uid=uid))
    await _delete(_PREV.format(uid=uid))
