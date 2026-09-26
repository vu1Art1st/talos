"""任务分发：优先投递 arq 队列，Redis 不可用时在进程内后台执行（开发/测试友好）。

`job_id` 为**投递级幂等**（P0-2）：arq 以 `_job_id` 作 Redis 键，同一 `job_id` 重复投递会被
拒绝（返回 None），因此「用户双击导出」「队列重试时重新入队」都不会产生第二个任务实例。
任务**执行级**幂等（重试不产生重复业务副作用）由任务函数自身保证：导出按 `job_id` 记录的状态
短路，通知按 `services.task_dedup` 的幂等键抢占。
"""
import asyncio
import logging

from fastapi import FastAPI

logger = logging.getLogger(__name__)


async def dispatch(app: FastAPI, func_name: str, *args, job_id: str | None = None) -> None:
    pool = getattr(app.state, "arq", None)
    if pool is not None:
        try:
            # job_id=None 时 arq 自生成 uuid（_job_id 为空即视为未指定）
            await pool.enqueue_job(func_name, *args, _job_id=job_id)
            return
        except Exception as exc:
            logger.warning("arq 投递失败，转为进程内执行: %s", exc)

    from app.workers.main import TASK_FUNCS

    func = TASK_FUNCS[func_name]
    asyncio.create_task(func({}, *args))
