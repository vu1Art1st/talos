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
from app.constants import ReportStatus
from app.core.config import settings
from app.core.outbound import assert_public_url
from app.core.timeutil import now
from app.db import async_session_maker
from app.models import ImportBatch, ImportRecord, ExportJob, Report, User
from app.services import report_meta
from app.services.docx_parser import parse_any_docx
from app.services.exporter import cleanup_stale_previews, convert_docx_to_pdf
from app.services.report_builder import build_report_docx

logger = logging.getLogger(__name__)


async def parse_import_task(ctx, batch_id: int) -> None:
    async with async_session_maker() as session:
        batch = await session.get(ImportBatch, batch_id)
        if batch is None:
            return
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
        except Exception as exc:  # 文件损坏 / 非 docx 等
            batch.status = "failed"
            batch.error = f"解析失败: {exc}"
            await session.commit()
            return

        batch.doc_kind = doc_kind
        batch.meta_json = meta

        success = failed = 0
        for seq, rec in enumerate(records, start=1):
            errors = rec.pop("errors", [])
            status = "error" if errors and not rec["title"] else "parsed"
            if status == "error":
                failed += 1
            else:
                success += 1
            session.add(ImportRecord(
                batch_id=batch_id,
                seq=seq,
                status=status,
                parse_error="；".join(errors),
                **rec,
            ))

        batch.total = len(records)
        batch.success = success
        batch.failed = failed
        if not records:
            batch.status = "failed"
            batch.error = (
                "未能从文档中解析出漏洞信息：支持标准导入模板或平台导出的渗透测试（复测）报告，"
                "请核对格式后重试"
            )
        else:
            batch.status = "parsed"
        await session.commit()


async def export_report_task(ctx, job_id: int) -> None:
    async with async_session_maker() as session:
        job = await session.get(ExportJob, job_id)
        if job is None:
            return
        job.status = "running"
        await session.commit()

        try:
            report = await session.get(Report, job.report_id)
            if report is None:
                raise ValueError("报告不存在")

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
            await asyncio.to_thread(build_report_docx, meta, vulns, sections, docx_path, assets, plan_urls)

            if job.fmt == "pdf":
                pdf_path = docx_path.replace(".docx", ".pdf")
                await convert_docx_to_pdf(docx_path, pdf_path)
                job.file_path = pdf_path
            else:
                job.file_path = docx_path

            job.status = "done"
            # 导出成功后报告导出版本 +1（编辑保存不影响该版本号）
            report.version += 1
            # 需求6：导出 Word 成功后报告定稿（已定稿/已完成的报告保持不变；PDF 导出不置定稿）
            if job.fmt == "docx" and report.status == ReportStatus.DRAFT.to_str():
                report.status = ReportStatus.FINAL.to_str()
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
            job.status = "failed"
            job.error = str(exc)
            job.finish_time = now()
            await session.commit()
            return

        job.finish_time = now()
        await session.commit()


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


async def send_notify_task(ctx, channel_type: str, config: dict, title: str, body: str) -> None:
    """渠道通知（F3）：企业微信/钉钉 webhook 与邮件，尽力而为（失败仅告警不重试）。

    出站前再次校验 webhook 目标（审计 TALOS-2026-003）：写入侧校验无法覆盖「存量渠道配置」
    与「DNS 记录事后变化」两种情况，故发送前再判一次；不允许跟随重定向（重定向目标同样可能
    指向内网）。校验不通过仅告警并跳过，不影响业务主流程。"""
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


async def cleanup_previews_task(ctx) -> None:
    """定期清理超过 30 分钟未再打开的临时预览 PDF。"""
    await asyncio.to_thread(cleanup_stale_previews, 30)


TASK_FUNCS = {
    "parse_import_task": parse_import_task,
    "export_report_task": export_report_task,
    "send_mail_task": send_mail_task,
    "send_notify_task": send_notify_task,
}


class WorkerSettings:
    functions = list(TASK_FUNCS.values())
    cron_jobs = [cron(cleanup_previews_task, minute=set(range(0, 60, 10)))]
    # 每次连接尝试的超时统一取 settings.REDIS_TIMEOUT（避免无超时挂起，见 G7）；
    # 重试次数保持 arq 默认（worker 需容忍 Redis 短暂不可用，属既有容错语义，不改）
    redis_settings = replace(
        RedisSettings.from_dsn(settings.REDIS_URL),
        conn_timeout=int(settings.REDIS_TIMEOUT),
    )
    max_jobs = 4
    job_timeout = 600
