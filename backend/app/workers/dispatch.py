"""任务分发：优先投递 arq 队列，Redis 不可用时在进程内后台执行（开发/测试友好）。"""
import asyncio
import logging

from fastapi import FastAPI

logger = logging.getLogger(__name__)


async def dispatch(app: FastAPI, func_name: str, *args) -> None:
    pool = getattr(app.state, "arq", None)
    if pool is not None:
        try:
            await pool.enqueue_job(func_name, *args)
            return
        except Exception as exc:
            logger.warning("arq 投递失败，转为进程内执行: %s", exc)

    from app.workers.main import TASK_FUNCS

    func = TASK_FUNCS[func_name]
    asyncio.create_task(func({}, *args))
