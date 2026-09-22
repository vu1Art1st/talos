"""G7 回归守卫：Redis 客户端必须带超时，且 Redis 不可达时降级路径可达。

背景（2026-09-18 实测）：当 Redis 处于「对端 DROP 报文」而非「主动拒绝连接」时，
未设置超时的 `aioredis` 客户端会停在 TCP 握手阶段**无限挂起**，`core/ratelimit.py`
的 `except` 降级分支永不触发 —— 登录失败计数 / PAT 限流的整条鉴权链随之卡死
（全量测试曾卡在 `tests/api/test_api_pat_open_api.py::test_pat_rate_limit`，即全量第 71 项）。

修复：`config.REDIS_TIMEOUT` + 客户端显式 `socket_connect_timeout` / `socket_timeout`。
本文件守卫该修复不被回退。
"""

import time

from app.core import ratelimit
from app.core.config import settings


async def test_redis_client_carries_socket_timeouts(monkeypatch):
    """客户端构造必须带**正的**连接/读写超时（防回退成无超时的默认值）。"""
    # 测试环境默认 DISABLE_REDIS=1（见 conftest）；本用例需要真实构造客户端，故显式关闭
    monkeypatch.setattr(settings, "DISABLE_REDIS", False)
    monkeypatch.setattr(ratelimit, "_redis", None)

    client = await ratelimit._get_redis()
    assert client is not None, "redis 依赖缺失时不适用；正常环境应可构造客户端"

    kwargs = client.connection_pool.connection_kwargs
    assert kwargs.get("socket_connect_timeout") == settings.REDIS_TIMEOUT
    assert kwargs.get("socket_timeout") == settings.REDIS_TIMEOUT
    assert settings.REDIS_TIMEOUT > 0, "超时必须为正数，否则降级路径仍不可达"


async def test_fallback_when_redis_unreachable(monkeypatch):
    """Redis 不可达时：调用必须有界返回，并落到进程内内存降级计数。"""
    # 指向本机关闭端口：等价于「Redis 不可用」，但不会依赖外部网络
    monkeypatch.setattr(settings, "REDIS_URL", "redis://127.0.0.1:6399/0")
    # 用例内用更小的超时以保持测试快速；只验证「有界 + 降级可达」，生产值由上一个用例守卫
    monkeypatch.setattr(settings, "REDIS_TIMEOUT", 0.5)
    # 关闭 DISABLE_REDIS 才能真正走「尝试连接 → 超时 → 降级」这条路径（而非直接降级）
    monkeypatch.setattr(settings, "DISABLE_REDIS", False)
    monkeypatch.setattr(ratelimit, "_redis", None)
    ratelimit._mem.clear()

    key = "g7:fallback"
    start = time.monotonic()
    await ratelimit.incr_failure(key, 60)
    await ratelimit.incr_failure(key, 60)
    count = await ratelimit.get_failures(key, 60)
    await ratelimit.clear_failures(key)
    elapsed = time.monotonic() - start

    assert count == 2, "Redis 不可用时必须落到进程内计数（降级路径可达）"
    assert await ratelimit.get_failures(key, 60) == 0, "clear_failures 后计数应归零"
    assert elapsed < 10, f"Redis 不可达时响应必须有界，实测 {elapsed:.1f}s"
