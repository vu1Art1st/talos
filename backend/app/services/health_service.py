"""健康检查依赖探测（P0-3）：`/api/health/ready` 的唯一实现。

依赖分级（口径见 ROADMAP P0-3）：
- **必需**：PostgreSQL（业务唯一事实源）；队列启用时 Redis 与 arq worker 也是必需依赖
  （`DISABLE_QUEUE=1` 的单机/测试形态下二者不参与判定）。
- **可选**：Gotenberg（PDF 转换）。不可用只降级为「PDF 导出不可用」，不应让整个实例 unready。

返回结构刻意保持「无敏感信息」：只给依赖名、ok 布尔与分类后的原因文案，
不含 DSN、密码、内网地址或完整异常堆栈（堆栈留在服务端日志）。
"""
import logging

import httpx
from fastapi import FastAPI
from sqlalchemy import text

from app.core.config import settings

logger = logging.getLogger(__name__)

DB = "database"
REDIS = "redis"
WORKER = "worker"
GOTENBERG = "gotenberg"

# arq worker 心跳键（与 workers/main.WorkerSettings.health_check_key 一致）
WORKER_HEALTH_KEY = "arq:health-check"

# 探测失败原因按异常类型归类，避免把原始异常（可能含连接串）透给调用方
_TIMEOUT_MARKERS = ("timeout", "timed out", "TimeoutError")
_REFUSED_MARKERS = ("refused", "ConnectError", "connection", "unreachable", "Name or service")


def _reason(exc: Exception) -> str:
    """把探测异常归类为不泄露内部信息的原因文案。"""
    text_ = f"{type(exc).__name__}: {exc}"
    if any(m.lower() in text_.lower() for m in _TIMEOUT_MARKERS):
        return "连接超时"
    if any(m.lower() in text_.lower() for m in _REFUSED_MARKERS):
        return "连接失败"
    return "探测失败"


async def _check_db() -> dict:
    from app.db import async_session_maker

    try:
        async with async_session_maker() as session:
            await session.execute(text("SELECT 1"))
        return {"ok": True, "required": True}
    except Exception as exc:  # noqa: BLE001  探测失败只上报状态，不抛给调用方
        logger.warning("健康检查：PostgreSQL 探测失败: %s", exc)
        return {"ok": False, "required": True, "reason": _reason(exc)}


async def _check_queue(app: FastAPI) -> dict:
    """队列启用时探测 Redis（arq 连接池）与 worker 心跳，二者均为必需依赖。"""
    if settings.DISABLE_QUEUE:
        return {REDIS: {"ok": True, "required": False, "reason": "队列已禁用"},
                WORKER: {"ok": True, "required": False, "reason": "队列已禁用"}}
    pool = getattr(app.state, "arq", None)
    if pool is None:
        # 启动时连接失败 → 已降级为进程内执行；ready 必须报不健康，避免流量打到无法投递的实例
        return {REDIS: {"ok": False, "required": True, "reason": "未建立队列连接"},
                WORKER: {"ok": False, "required": True, "reason": "未建立队列连接"}}
    try:
        await pool.ping()
    except Exception as exc:  # noqa: BLE001
        logger.warning("健康检查：Redis 探测失败: %s", exc)
        return {REDIS: {"ok": False, "required": True, "reason": _reason(exc)},
                WORKER: {"ok": False, "required": True, "reason": "Redis 不可用"}}
    try:
        alive = await pool.get(WORKER_HEALTH_KEY) is not None
    except Exception as exc:  # noqa: BLE001
        logger.warning("健康检查：worker 心跳读取失败: %s", exc)
        alive = False
    return {
        REDIS: {"ok": True, "required": True},
        # 心跳键由 arq worker 按 health_check_interval 续期，缺失说明无存活 worker
        WORKER: ({"ok": True, "required": True} if alive
                 else {"ok": False, "required": True, "reason": "无存活 worker 心跳"}),
    }


async def _check_gotenberg() -> dict:
    """Gotenberg 为可选能力：失败只标注状态，不影响整体 ready。"""
    try:
        async with httpx.AsyncClient(timeout=settings.HEALTH_PROBE_TIMEOUT) as client:
            resp = await client.get(f"{settings.GOTENBERG_URL}/health")
        return {"ok": resp.status_code < 500, "required": False}
    except Exception as exc:  # noqa: BLE001
        logger.info("健康检查：Gotenberg 不可用（可选依赖）: %s", exc)
        return {"ok": False, "required": False, "reason": _reason(exc)}


async def probe_dependencies(app: FastAPI) -> tuple[dict, bool]:
    """返回 (逐项依赖状态, 是否就绪)。就绪 = 所有必需依赖均 ok。"""
    checks = {DB: await _check_db()}
    checks.update(await _check_queue(app))
    checks[GOTENBERG] = await _check_gotenberg()
    ready = all(c["ok"] for c in checks.values() if c["required"])
    return checks, ready
