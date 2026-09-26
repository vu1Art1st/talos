"""arq 后台任务：Word 解析 / 报告导出 / 邮件发送 / 渠道通知（webhook+邮件）。

启动 worker: arq app.workers.main.WorkerSettings
"""
import asyncio
import logging
import smtplib
from dataclasses import replace
from email.header import Header
from email.mime.text import MIMEText

import httpx
from arq import cron
from arq.connections import RedisSettings
from app.core.config import settings
from app.core.outbound import assert_public_url
from app.core.timeutil import now
from app.db import async_session_maker
from app.models import ImportBatch, ImportRecord, ExportJob, Report, User
from app.services import report_meta, task_dedup, task_lifecycle
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
            # 生成 docx / 转 PDF 是长耗时步骤：先续租，避免被启动回收扫描判为孤儿任务
            task_lifecycle.heartbeat(job)
            await session.commit()
            await asyncio.to_thread(build_report_docx, meta, vulns, sections, docx_path, assets, plan_urls)

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


def _send_mail_sync(to: list[str], subject: str, body: str) -> None:
    if not settings.SMTP_HOST or not to:
        return
    msg = MIMEText(body, "html", "utf-8")
    msg["Subject"] = Header(subject, "utf-8")
    msg["From"] = settings.SMTP_FROM or settings.SMTP_USER
    msg["To"] = ",".join(to)
    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15) as server:
        if settings.SMTP_USER:
            server.login(settings.SMTP_USER, settings.SMTP_PASS)
        server.sendmail(msg["From"], to, msg.as_string())


async def send_mail_task(ctx, to: list[str], subject: str, body: str) -> None:
    await asyncio.to_thread(_send_mail_sync, to, subject, body)


async def send_notify_task(
    ctx, channel_type: str, config: dict, title: str, body: str, dedup_key: str = "",
) -> None:
    """渠道通知（F3）：企业微信/钉钉 webhook 与邮件，尽力而为（失败仅告警不重试）。

    **幂等（P0-2）**：`dedup_key` 非空时先抢占（`services.task_dedup`）；抢占失败说明同一
    业务事件的通知已经投递过（队列重试 / 进程内重放），直接返回，不产生重复通知。
    发送失败则释放幂等键，使重试仍然有效（否则一次网络抖动会让通知永久丢失）。

    出站前再次校验 webhook 目标（审计 TALOS-2026-003）：写入侧校验无法覆盖「存量渠道配置」
    与「DNS 记录事后变化」两种情况，故发送前再判一次；不允许跟随重定向（重定向目标同样可能
    指向内网）。校验不通过仅告警并跳过，不影响业务主流程。"""
    if dedup_key and not await _claim_notify_dedup(dedup_key):
        logger.info("通知重复投递已忽略 dedup_key=%s", dedup_key)
        return
    try:
        if channel_type in ("wecom", "dingtalk"):
            url = (config or {}).get("url") or ""
            if not url:
                return
            try:
                url = assert_public_url(url, field="webhook 地址")
            except ValueError as exc:
                logger.warning("webhook 目标被拒绝，已跳过发送 type=%s: %s", channel_type, exc)
                return
            if channel_type == "wecom":
                payload = {"msgtype": "markdown", "markdown": {"content": f"**{title}**\n{body}"}}
            else:
                payload = {"msgtype": "markdown", "markdown": {"title": title, "text": f"#### {title}\n\n{body}"}}
            async with httpx.AsyncClient(timeout=10, follow_redirects=False) as client:
                resp = await client.post(url, json=payload)
                if resp.status_code != 200:
                    logger.warning("webhook 通知发送失败 type=%s status=%s", channel_type, resp.status_code)
        elif channel_type == "email":
            recipients = (config or {}).get("recipients") or []
            html = f"<p><strong>{title}</strong></p>" + "".join(
                f"<p>{line}</p>" for line in body.splitlines() if line.strip()
            )
            await asyncio.to_thread(_send_mail_sync, recipients, title, html)
    except Exception as exc:  # noqa: BLE001  通知失败不影响业务
        logger.warning("通知发送异常 type=%s: %s", channel_type, exc)
        if dedup_key:
            # 发送失败释放幂等键：否则队列重试会被自己的幂等键挡住，通知永久丢失
            await _release_notify_dedup(dedup_key)


async def _claim_notify_dedup(key: str) -> bool:
    """抢占通知幂等键（独立短事务并在抢占后立即提交，保证跨进程可见）。"""
    async with async_session_maker() as session:
        claimed = await task_dedup.claim_dedup_key(session, key)
        await session.commit()
        return claimed


async def _release_notify_dedup(key: str) -> None:
    """释放通知幂等键（发送失败时调用，使重试仍可执行）。"""
    async with async_session_maker() as session:
        await task_dedup.release_dedup_key(session, key)
        await session.commit()


async def cleanup_previews_task(ctx) -> None:
    """定期清理超过 30 分钟未再打开的临时预览 PDF，并回收过期的任务幂等键。"""
    await asyncio.to_thread(cleanup_stale_previews, 30)
    async with async_session_maker() as session:
        removed = await task_dedup.cleanup_dedup_keys(session)
        await session.commit()
    if removed:
        logger.info("已回收过期任务幂等键 %s 条", removed)


TASK_FUNCS = {
    "parse_import_task": parse_import_task,
    "export_report_task": export_report_task,
    "send_mail_task": send_mail_task,
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
