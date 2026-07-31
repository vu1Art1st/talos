"""arq 后台任务：Word 解析 / 报告导出 / 邮件发送。

启动 worker: arq app.workers.main.WorkerSettings
"""
import asyncio
import smtplib
from datetime import datetime
from email.header import Header
from email.mime.text import MIMEText

from arq import cron
from arq.connections import RedisSettings
from sqlalchemy import select

from app.core.config import settings
from app.core.timeutil import utcnow
from app.db import async_session_maker
from app.models import ImportBatch, ImportRecord, ExportJob, Report, Vul
from app.services.docx_parser import parse_any_docx
from app.services.exporter import cleanup_stale_previews, convert_docx_to_pdf
from app.services.report_builder import build_report_docx


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
            batch.error = "未能从文档中解析出漏洞信息：支持标准导入模板或平台导出的渗透测试（复测）报告，请核对格式后重试"
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

            meta = {
                "title": report.title,
                "project_name": report.project_name,
                "customer": report.customer,
                "author": report.author,
                "test_start": report.test_start,
                "test_end": report.test_end,
                "target_ip": report.target_ip,
                "status": report.status,
            }
            sections = [
                {"title": s.title, "content_html": s.content_html, "vul_id": s.vul_id}
                for s in report.sections
            ]
            vul_ids = [s.vul_id for s in report.sections if s.vul_id]
            vulns: list[dict] = []
            assets: list[dict] = []
            if vul_ids:
                rows = (await session.execute(select(Vul).where(Vul.id.in_(vul_ids)))).scalars().all()
                by_id = {v.id: v for v in rows}
                vulns = [
                    {
                        "id": v.id,
                        "title": v.title, "vul_type": v.vul_type, "level": v.level,
                        "status": v.status, "affected_url": v.affected_url, "is_retest": v.is_retest,
                        "retest_html": v.retest_html,
                    }
                    for vid in vul_ids if (v := by_id.get(vid))
                ]
                # 聚合关联资产（去重）供模板「测试目标」表使用
                seen: set[int] = set()
                for v in rows:
                    for a in v.assets:
                        if a.id in seen:
                            continue
                        seen.add(a.id)
                        assets.append({
                            "name": a.name,
                            "public_urls": a.public_urls or [],
                            "internal_urls": a.internal_urls or [],
                        })

            export_dir = settings.storage_sub("exports")
            stamp = datetime.now().strftime("%Y%m%d%H%M%S")
            docx_path = str(export_dir / f"report_{report.id}_{stamp}.docx")
            await asyncio.to_thread(build_report_docx, meta, vulns, sections, docx_path, assets)

            if job.fmt == "pdf":
                pdf_path = docx_path.replace(".docx", ".pdf")
                await convert_docx_to_pdf(docx_path, pdf_path)
                job.file_path = pdf_path
            else:
                job.file_path = docx_path

            job.status = "done"
        except Exception as exc:
            job.status = "failed"
            job.error = str(exc)
        finally:
            job.finish_time = utcnow()
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


async def cleanup_previews_task(ctx) -> None:
    """定期清理超过 30 分钟未再打开的临时预览 PDF。"""
    await asyncio.to_thread(cleanup_stale_previews, 30)


TASK_FUNCS = {
    "parse_import_task": parse_import_task,
    "export_report_task": export_report_task,
    "send_mail_task": send_mail_task,
}


class WorkerSettings:
    functions = list(TASK_FUNCS.values())
    cron_jobs = [cron(cleanup_previews_task, minute=set(range(0, 60, 10)))]
    redis_settings = RedisSettings.from_dsn(settings.REDIS_URL)
    max_jobs = 4
    job_timeout = 600
