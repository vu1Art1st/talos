"""后台任务生命周期（P0-3）：租约、心跳、重试退避、死信与启动回收。

**为什么需要**：`ExportJob` / `ImportBatch` 原先只有「业务写入驱动的状态」，
worker 进程在执行中崩溃时记录会永久停在 `running` / `parsing`，界面上表现为「一直生成中」，
既不会失败也不会重试。

方案（**不合并为统一任务表**）：两张表的业务语义（导出版本、报告章节、解析记录）差异大，
合并会牵动报告与导入两条主链路的全部读写点；改为在两表上加**同一组生命周期列**
（`attempts` / `last_heartbeat` / `lease_until` / `next_retry_at` / `dead_letter_reason`），
由本模块提供统一的状态机实现，避免两处各写一套：

    pending(parsed) --start_lease--> running(parsing) --success--> done(confirmed)
                                            |  ^
                         可重试失败: plan_retry |  | 心跳续租
                                            v  |
                                     pending + next_retry_at
                         永久失败 / 超过最大次数: mark_dead_letter --> failed

`create_time` 之前的行（无租约列）在启动回收时同样按「孤儿任务」处理。
"""
import logging
from datetime import timedelta

from sqlalchemy import and_, or_, select

from app.core.config import settings
from app.core.timeutil import now
from app.db import async_session_maker
from app.models import ExportJob, ImportBatch

logger = logging.getLogger(__name__)

# 兜底扫描间隔（秒）：进程内执行形态由 API 侧周期任务使用；worker 侧用 cron 同频调用
SWEEP_INTERVAL_SECONDS = 300

# 任务类型 → (模型, 运行中状态, 可重试/排队状态, 已被业务消费的状态)
_TASK_KINDS = {
    "export": (ExportJob, ("running",), "pending", ("done",)),
    "import": (ImportBatch, ("parsing",), "pending", ("confirmed",)),
}

# 永不重试的永久错误特征（文件损坏/权限/数据缺失：重试没有意义）
_PERMANENT_MARKERS = (
    "file not found", "no such file", "permission", "not a zip", "badzipfile",
    "不是有效的", "不存在", "unsupported", "unsupportedformat",
)


class PermanentTaskError(Exception):
    """标记为永久失败（不重试，直接进死信）。任务内部可主动抛出以跳过重试。"""


def is_retryable(exc: BaseException) -> bool:
    """判断异常是否可重试：文件损坏 / 权限 / 数据缺失等永久错误不重试。"""
    if isinstance(exc, PermanentTaskError):
        return False
    text = f"{type(exc).__name__}: {exc}".lower()
    return not any(marker in text for marker in _PERMANENT_MARKERS)


def backoff_seconds(attempts: int) -> int:
    """指数退避：第 1 次失败等 base，第 2 次 2×base，第 3 次 4×base（封顶 1 小时）。"""
    base = max(settings.TASK_BACKOFF_SECONDS, 1)
    return min(base * (2 ** max(attempts - 1, 0)), 3600)


def start_lease(row) -> None:
    """任务开始：记一次尝试、写入心跳与租约到期时间（供回收扫描识别孤儿任务）。"""
    started = now()
    row.attempts = int(getattr(row, "attempts", 0) or 0) + 1
    row.last_heartbeat = started
    row.lease_until = started + timedelta(seconds=settings.TASK_LEASE_SECONDS)
    row.next_retry_at = None
    row.dead_letter_reason = ""


def heartbeat(row) -> None:
    """续租（长任务在关键阶段调用，避免被回收扫描判为孤儿）。"""
    row.last_heartbeat = now()
    row.lease_until = now() + timedelta(seconds=settings.TASK_LEASE_SECONDS)


def finish(row) -> None:
    """任务成功：清空租约与重试计划（业务状态由调用方置为 done / parsed）。"""
    row.lease_until = None
    row.next_retry_at = None
    row.dead_letter_reason = ""
    if hasattr(row, "finish_time"):
        row.finish_time = now()


def mark_dead_letter(row, reason: str) -> None:
    """永久失败 / 超过最大尝试次数：标记失败并保留原因，不再自动重试。"""
    row.status = "failed"
    row.error = reason or row.error or "任务失败"
    row.dead_letter_reason = reason or "任务失败"
    row.lease_until = None
    row.next_retry_at = None
    row.finish_time = now()


def plan_retry(row, exc: BaseException) -> bool:
    """失败后决定重试还是进死信；返回是否安排重试（可重试）。"""
    reason = f"{type(exc).__name__}: {exc}"
    attempts = int(getattr(row, "attempts", 0) or 0)
    if not is_retryable(exc) or attempts >= max(settings.TASK_MAX_ATTEMPTS, 1):
        mark_dead_letter(row, reason)
        return False
    row.status = "pending"
    row.error = reason
    row.dead_letter_reason = ""
    row.lease_until = None
    row.next_retry_at = now() + timedelta(seconds=backoff_seconds(attempts))
    return True


def _stale_condition(model, running_states: tuple[str, ...]):
    """孤儿任务判定：处于运行中状态，且租约已过期（或从未写入租约的存量行）。"""
    grace = timedelta(seconds=settings.TASK_LEASE_SECONDS)
    return and_(
        model.status.in_(running_states),
        or_(
            and_(model.lease_until.is_not(None), model.lease_until < now()),
            # 存量行（迁移前写入）没有租约：按「创建时间已超过一个租约周期」保守判定
            and_(
                model.lease_until.is_(None),
                model.last_heartbeat.is_(None),
                model.create_time < now() - grace,
            ),
        ),
    )


def _recover_row(row, queued_state: str) -> str:
    """回收单条孤儿任务：可重试者回到排队态并安排退避重试，达上限者进死信。"""
    attempts = int(getattr(row, "attempts", 0) or 0)
    if attempts >= max(settings.TASK_MAX_ATTEMPTS, 1):
        mark_dead_letter(row, f"worker 中断且已达最大尝试次数（{attempts}）")
        return "dead"
    row.status = queued_state
    row.lease_until = None
    row.next_retry_at = now() + timedelta(seconds=backoff_seconds(attempts + 1))
    row.error = "worker 中断，任务已回收待重试"
    return "requeued"


async def recover_stale_tasks() -> dict:
    """启动时执行一次：回收超租约的 running/parsing 任务，返回各类计数。

    必须在**同一个 session** 内查询并修改（ORM 对象只在所属 session 中跟踪；
    跨 session 修改不会落库）。已到期（`next_retry_at <= now`）的排队任务不在此处理，
    由 `redispatch_recovered` / worker 定期任务负责重新执行。
    """
    summary = {"requeued": 0, "dead": 0, "tasks": []}
    async with async_session_maker() as session:
        for kind, (model, running_states, queued_state, _done) in _TASK_KINDS.items():
            rows = (await session.execute(
                select(model).where(_stale_condition(model, running_states)).limit(500)
            )).scalars().all()
            requeued = dead = 0
            for row in rows:
                if _recover_row(row, queued_state) == "dead":
                    dead += 1
                else:
                    requeued += 1
            if requeued or dead:
                logger.warning("任务回收 kind=%s 重新排队=%s 死信=%s", kind, requeued, dead)
                summary["tasks"].append({"kind": kind, "requeued": requeued, "dead": dead})
            summary["requeued"] += requeued
            summary["dead"] += dead
        await session.commit()
    return summary


async def due_task_ids() -> tuple[list[int], list[int]]:
    """已到期、等待重新执行的 (导出任务 id 列表, 导入批次 id 列表)。"""
    async with async_session_maker() as session:
        exports = (await session.execute(
            select(ExportJob.id).where(
                ExportJob.status == "pending",
                ExportJob.next_retry_at.is_not(None),
                ExportJob.next_retry_at <= now(),
            ).limit(200)
        )).scalars().all()
        imports = (await session.execute(
            select(ImportBatch.id).where(
                ImportBatch.status == "pending",
                ImportBatch.next_retry_at.is_not(None),
                ImportBatch.next_retry_at <= now(),
            ).limit(200)
        )).scalars().all()
    return list(exports), list(imports)


async def redispatch_recovered(app) -> None:
    """把到期的待重试任务重新投递（队列可用时走 arq，否则进程内执行）。

    投递键带 `:retry` 后缀：arq 的原任务键（`export:<id>`）在结果保留期内仍然存在，
    复用同一 `_job_id` 会被 arq 拒绝入队，导致重试永远不执行。
    """
    from app.workers.dispatch import dispatch

    exports, imports = await due_task_ids()
    for job_id in exports:
        await dispatch(app, "export_report_task", job_id, job_id=f"export:{job_id}:retry")
    for batch_id in imports:
        await dispatch(app, "parse_import_task", batch_id, job_id=f"parse:{batch_id}:retry")


async def recover_and_redispatch(app) -> dict:
    """启动/周期扫描入口：先回收孤儿任务，再重新投递到期待重试任务。"""
    summary = await recover_stale_tasks()
    await redispatch_recovered(app)
    return summary


async def run_due_tasks(ctx) -> int:
    """worker 侧兜底扫描：直接执行到期的待重试任务，返回执行条数。

    worker 进程没有 FastAPI app（无法 `dispatch`），故直接调用任务函数；
    该路径与队列投递的重复风险由任务自身的幂等守卫（状态短路 / 幂等键）兜住。
    """
    from app.workers.main import TASK_FUNCS

    exports, imports = await due_task_ids()
    for job_id in exports:
        await TASK_FUNCS["export_report_task"](ctx, job_id)
    for batch_id in imports:
        await TASK_FUNCS["parse_import_task"](ctx, batch_id)
    return len(exports) + len(imports)
