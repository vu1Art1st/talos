"""arq 后台任务：Word 解析 / 报告导出 / 渠道通知投递 / SLA 扫描 / 定期清理。

启动 worker: arq app.workers.main.WorkerSettings
"""
import asyncio
import logging
from dataclasses import replace

from arq import cron
from arq.connections import RedisSettings
from app.core.config import settings
from app.core.timeutil import now
from app.db import async_session_maker
from app.models import (
    ExportJob,
    ImportBatch,
    ImportRecord,
    NotifyDelivery,
    Report,
    ReportTemplate,
    User,
)
from app.services import (
    idempotency,
    message_service,
    notify_service,
    report_meta,
    sla_service,
    task_dedup,
    task_lifecycle,
    template_service,
)
from app.services.docx_parser import parse_any_docx
from app.services.exporter import cleanup_stale_previews, convert_docx_to_pdf
from app.services.report_builder import build_report_docx

logger = logging.getLogger(__name__)


async def _handle_task_failure(session, row, exc: Exception, ident: str) -> bool:
    """失败收尾（P0-3）：可重试 → 记退避重试并返回 True（由调用方抛出交给队列重试）；
    永久错误或超过最大尝试次数 → 进死信并返回 False（不重试，保留原因）。"""
    retryable = task_lifecycle.plan_retry(row, exc)
    await session.commit()
    if retryable:
        logger.warning("任务失败，已安排退避重试 %s attempts=%s: %s", ident, row.attempts, exc)
    else:
        logger.error("任务永久失败，已进死信 %s: %s", ident, exc)
    return retryable


def _persist_parsed_records(session, batch_id: int, records: list[dict]) -> tuple[int, int]:
    """解析结果落库（ImportRecord），返回 (成功数, 失败数)。"""
    success = failed = 0
    for seq, rec in enumerate(records, start=1):
        errors = rec.pop("errors", [])
        status = "error" if errors and not rec["title"] else "parsed"
        if status == "error":
            failed += 1
        else:
            success += 1
        session.add(ImportRecord(
            batch_id=batch_id, seq=seq, status=status,
            parse_error="；".join(errors), **rec,
        ))
    return success, failed


async def parse_import_task(ctx, batch_id: int) -> None:
    """Word 导入解析：租约 + 心跳 + 可重试/永久错误分流（见 services/task_lifecycle.py）。"""
    async with async_session_maker() as session:
        batch = await session.get(ImportBatch, batch_id)
        if batch is None:
            return
        if batch.status in ("parsed", "confirmed"):
            return  # 幂等：已解析 / 已入库的批次不重复解析（重试或重复投递时短路）
        task_lifecycle.start_lease(batch)
        batch.status = "parsing"
        await session.commit()

        # 导入解析出的图片统一落到公开图片目录，避免暴露导入原始文档所在目录
        image_dir = settings.storage_sub("uploads", "images")
        try:
            doc_kind, meta, records = await asyncio.to_thread(
                parse_any_docx,
                batch.file_path,
                str(image_dir),
                "/storage/uploads/images",
                batch.filename,
            )
        except Exception as exc:  # 文件损坏 / 非 docx 等：按可重试性分流
            if await _handle_task_failure(session, batch, exc, f"batch_id={batch_id}"):
                raise
            return

        batch.doc_kind = doc_kind
        batch.meta_json = meta
        batch.total = len(records)
        batch.success, batch.failed = _persist_parsed_records(session, batch_id, records)
        if not records:
            task_lifecycle.mark_dead_letter(
                batch,
                "未能从文档中解析出漏洞信息：支持标准导入模板或平台导出的渗透测试（复测）报告，"
                "请核对格式后重试",
            )
        else:
            batch.status = "parsed"
            task_lifecycle.finish(batch)
        await session.commit()
        logger.info(
            "导入解析完成 batch_id=%s records=%s status=%s", batch_id, len(records), batch.status,
        )


async def export_report_task(ctx, job_id: int) -> None:
    """报告导出：租约 + 心跳 + 可重试/永久错误分流（见 services/task_lifecycle.py）。"""
    async with async_session_maker() as session:
        job = await session.get(ExportJob, job_id)
        if job is None:
            return
        # 执行级幂等（P0-2）：已完成的导出在队列重试/重复投递下直接短路，
        # 否则会重复生成文件并把报告导出版本号再加一次。
        if job.status == "done":
            return
        task_lifecycle.start_lease(job)
        job.status = "running"
        await session.commit()

        try:
            report = await session.get(Report, job.report_id)
            if report is None:
                raise task_lifecycle.PermanentTaskError("报告不存在")

            # 发起导出报告的账号：版本变更记录「修改人」列使用（而非报告作者）
            generator = None
            if job.creator_id is not None:
                gu = await session.get(User, job.creator_id)
                if gu is not None:
                    generator = gu.realname or gu.username or ""
            # 关联测试计划（参测人员 / 版本记录清单）与 meta / 章节 / 漏洞与资产构建
            # 统一走 services.report_meta（与导入后自动导出共用同一实现）。
            # 手动导出不注入 report_time，封面与版本记录的基准由 report_builder 取当前时间。
            plan = await report_meta.resolve_plan(session, report)
            meta = await report_meta.build_export_meta(
                session, report, plan=plan, generator=generator
            )
            sections = report_meta.build_sections(report)
            vulns, assets = await report_meta.collect_vulns_and_assets(session, sections)
            plan_urls = report_meta.collect_plan_urls(plan)

            export_dir = settings.storage_sub("exports")
            stamp = now().strftime("%Y%m%d%H%M%S")
            docx_path = str(export_dir / f"report_{report.id}_{stamp}.docx")
            # P1-4 模板中心：按导出任务记录的模板生成；无模板/文件缺失时回退包内默认模板，
            # 保证「不存在可用模板时系统仍可导出」与「DOCX/PDF 使用同一模板版本」。
            tpl_row = (
                await session.get(ReportTemplate, job.template_id)
                if job.template_id is not None else None
            )
            template_path = template_service.template_file(tpl_row)
            # 生成 docx / 转 PDF 是长耗时步骤：先续租，避免被启动回收扫描判为孤儿任务
            task_lifecycle.heartbeat(job)
            await session.commit()
            await asyncio.to_thread(
                build_report_docx, meta, vulns, sections, docx_path, assets, plan_urls, template_path,
            )

            if job.fmt == "pdf":
                pdf_path = docx_path.replace(".docx", ".pdf")
                task_lifecycle.heartbeat(job)
                await session.commit()
                await convert_docx_to_pdf(docx_path, pdf_path)
                job.file_path = pdf_path
            else:
                job.file_path = docx_path

            job.status = "done"
            # 导出成功后报告导出版本 +1（编辑保存不影响该版本号）
            report.version += 1
            # 版本号 +1 与 update_time 刷新（onupdate）会改变报告指纹，
            # 需 flush+refresh 后以最终状态更新导出任务指纹，供下次导出前重复判断
            await session.flush()
            await session.refresh(report)
            job.report_snapshot = report.fingerprint()
        except Exception as exc:
            # 先回滚失败事务：PostgreSQL 事务报错后进入 aborted 状态，
            # 不 rollback 直接 commit 会抛 InFailedSQLTransactionError，任务将永远卡在 running。
            await session.rollback()
            job = await session.get(ExportJob, job_id)
            if job is None:
                return
            if await _handle_task_failure(session, job, exc, f"job_id={job_id}"):
                raise
            return

        task_lifecycle.finish(job)
        await session.commit()
        logger.info("报告导出完成 job_id=%s report_id=%s fmt=%s", job_id, job.report_id, job.fmt)


async def send_notify_task(ctx, delivery_id: int) -> None:
    """渠道通知投递（F3 + P1-3）：按投递记录执行一次外发。

    - 投递记录是幂等的锚点：`job_id=f"notify:{id}"` 保证同一记录不会被重复入队；
    - 失败**不抛异常**：可重试错误写入 `next_retry_at`（`retry_deliveries_task` 会重投），
      永久错误或超过上限进死信；状态与错误均可查询。
    """
    async with async_session_maker() as session:
        row = await session.get(NotifyDelivery, delivery_id)
        if row is None or row.status in ("success", "dead"):
            return
        await notify_service.send_delivery(session, row)
        await session.commit()
        logger.info(
            "通知投递完成 delivery_id=%s status=%s attempts=%s",
            delivery_id, row.status, row.attempts,
        )


async def retry_deliveries_task(ctx) -> None:
    """重投到期的失败通知（P1-3）：进程重启后待重试记录仍在库中，由本任务继续投递。"""
    async with async_session_maker() as session:
        n = await notify_service.retry_due_deliveries(session)
        await session.commit()
    if n:
        logger.info("已重投到期通知 %s 条", n)


async def sla_scan_task(ctx) -> None:
    """SLA 到期前提醒与逾期升级（P1-1）。

    同一漏洞同一到期时间的同一类提醒只产生一次（`task_dedup` 幂等键
    `sla:<kind>:<vul_id>:<due_at>`）；站内消息与渠道通知同源触发。
    """
    async with async_session_maker() as session:
        config = await sla_service.get_config(session)
        if not config.enabled:
            return
        reminders = await sla_service.collect_reminders(session, config)
        fired = 0
        for vul, kind in reminders:
            due_key = vul.due_at.strftime("%Y%m%d%H%M") if vul.due_at else ""
            key = f"sla:{kind}:{vul.id}:{due_key}"
            if not await task_dedup.claim_dedup_key(session, key):
                continue
            await session.flush()
            info = sla_service.evaluate(vul, config)
            label = "即将到期" if kind == "sla_due_soon" else "已逾期"
            due_text = vul.due_at.strftime("%Y-%m-%d %H:%M") if vul.due_at else ""
            await message_service.create_message(
                session, vul.submitter_id, "sla", f"SLA {label}：{vul.title}",
                content=(
                    f"修复截止时间 {due_text}，当前状态：{label}。"
                    + (f"已逾期 {info['sla_overdue_days']} 天。" if kind == "sla_overdue" else "")
                ),
                link=f"/vulns/{vul.id}",
            )
            await notify_service.notify_inline(
                session, kind, title=vul.title, due_at=due_text,
                overdue_days=info["sla_overdue_days"],
            )
            fired += 1
        await session.commit()
    if fired:
        logger.info("SLA 扫描：已发出 %s 条到期/逾期提醒", fired)


async def cleanup_previews_task(ctx) -> None:
    """定期清理临时预览 PDF、过期幂等键、超保留期消息、投递记录与 API 幂等键。"""
    await asyncio.to_thread(cleanup_stale_previews, 30)
    async with async_session_maker() as session:
        removed = await task_dedup.cleanup_dedup_keys(session)
        messages = await message_service.cleanup_messages(session)
        deliveries = await notify_service.cleanup_deliveries(session)
        api_keys = await idempotency.cleanup(session)
        await session.commit()
    if removed or messages or deliveries or api_keys:
        logger.info(
            "清理完成：幂等键=%s 消息=%s 投递记录=%s 接口幂等键=%s",
            removed, messages, deliveries, api_keys,
        )


TASK_FUNCS = {
    "parse_import_task": parse_import_task,
    "export_report_task": export_report_task,
    "send_notify_task": send_notify_task,
}


async def recover_tasks_task(ctx) -> None:
    """兜底扫描（P0-3，cron）：回收超租约任务并执行到期的待重试任务。

    API 进程启动时已回收一次，但「失败→退避等待」的任务若没有后续扫描就会一直停在
    `pending`；worker 侧按 `SWEEP_INTERVAL_SECONDS` 同频兜底，保证重试一定被执行。
    """
    summary = await task_lifecycle.recover_stale_tasks()
    if summary["requeued"] or summary["dead"]:
        logger.warning(
            "周期任务回收：重新排队=%s 死信=%s", summary["requeued"], summary["dead"],
        )
    ran = await task_lifecycle.run_due_tasks(ctx)
    if ran:
        logger.info("周期兜底：已重新执行到期任务 %s 个", ran)


class WorkerSettings:
    functions = list(TASK_FUNCS.values())
    cron_jobs = [
        cron(cleanup_previews_task, minute=set(range(0, 60, 10))),
        # 兜底扫描（P0-3）：与 SWEEP_INTERVAL_SECONDS=300 同频
        cron(recover_tasks_task, minute=set(range(0, 60, 5))),
        # 通知投递重试（P1-3）：待重试记录持久化在库，进程重启后由本任务继续投递
        cron(retry_deliveries_task, minute=set(range(0, 60, 5))),
        # SLA 到期前提醒与逾期升级（P1-1）：每 15 分钟扫一次，幂等键保证同一次变化只提醒一次
        cron(sla_scan_task, minute=set(range(0, 60, 15))),
    ]
    # 每次连接尝试的超时统一取 settings.REDIS_TIMEOUT（避免无超时挂起，见 G7）；
    # 重试次数保持 arq 默认（worker 需容忍 Redis 短暂不可用，属既有容错语义，不改）
    redis_settings = replace(
        RedisSettings.from_dsn(settings.REDIS_URL),
        conn_timeout=int(settings.REDIS_TIMEOUT),
    )
    max_jobs = 4
    job_timeout = 600
    # 存活心跳（P0-3）：arq 默认 3600s 太粗，ready 探针无法据此判断 worker 是否在跑；
    # 30s 续期 + TTL 61s，与 services/health_service.WORKER_HEALTH_KEY 对应
    health_check_interval = 30
    health_check_key = "arq:health-check"
    # 队列级重试次数（> tasks 的 TASK_MAX_ATTEMPTS=3，由任务自身先判定死信）
    max_tries = 5
