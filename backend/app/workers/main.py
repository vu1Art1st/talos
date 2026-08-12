"""arq 后台任务：Word 解析 / 报告导出 / 邮件发送。

启动 worker: arq app.workers.main.WorkerSettings
"""
import asyncio
import smtplib
from email.header import Header
from email.mime.text import MIMEText

from arq import cron
from arq.connections import RedisSettings
from sqlalchemy import func, select

from app.constants import ReportStatus
from app.core.config import settings
from app.core.timeutil import now
from app.db import async_session_maker
from app.models import ImportBatch, ImportRecord, ExportJob, Report, TestingPlan, User, Vul
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
                # 复测判定口径与 plan_service.is_retest_report_title 一致：标题含「复测」
                "is_retest": "复测" in (report.title or ""),
            }
            # 发起导出报告的账号：版本变更记录「修改人」列使用（而非报告作者）
            if job.creator_id is not None:
                gu = await session.get(User, job.creator_id)
                if gu is not None:
                    meta["generator"] = gu.realname or gu.username or ""
            # 关联测试计划：参测人员列表 + 版本记录清单（供版本变更记录/人员表格使用）
            plan = None
            if report.testing_plan_id is not None:
                plan = await session.get(TestingPlan, report.testing_plan_id)
            testers: list[str] = []
            report_records: list[dict] = []
            if plan is not None:
                for u in plan.testers:
                    name = (u.realname or u.username or "").strip()
                    if name and name not in testers:
                        testers.append(name)
                # 该计划下的全部报告（初测 1 份 + 每轮复测各 1 份），按创建顺序对齐版本记录。
                # 以「报告」为版本号唯一数据源：手动流转/导入产生的无报告复测轮次不再计入版本号，
                # 保证版本号与实际复测报告数量严格一致
                plan_reports = (
                    await session.execute(
                        select(Report)
                        .where(Report.testing_plan_id == plan.id)
                        .order_by(Report.create_time, Report.id)
                    )
                ).scalars().all()
                # 一次查询这些报告最近一次成功导出的时间
                report_ids = [pr.id for pr in plan_reports]
                last_done: dict[int, str] = {}
                if report_ids:
                    rows = (
                        await session.execute(
                            select(ExportJob.report_id, func.max(ExportJob.finish_time))
                            .where(
                                ExportJob.report_id.in_(report_ids),
                                ExportJob.status == "done",
                            )
                            .group_by(ExportJob.report_id)
                        )
                    ).all()
                    for rid, ft in rows:
                        if ft is not None:
                            last_done[rid] = ft.strftime("%Y-%m-%d")
                export_date_str = now().strftime("%Y-%m-%d")
                for pr in plan_reports:
                    if pr.id == report.id:
                        rdate = export_date_str  # 当前报告取本次导出时间
                    elif pr.id in last_done:
                        rdate = last_done[pr.id]
                    elif pr.create_time is not None:
                        rdate = pr.create_time.strftime("%Y-%m-%d")
                    else:
                        rdate = ""
                    creator_name = ""
                    if pr.creator_id is not None:
                        cu = await session.get(User, pr.creator_id)
                        if cu is not None:
                            creator_name = cu.realname or cu.username or ""
                    if not creator_name:
                        creator_name = pr.author or ""
                    report_records.append({
                        # 复测判定与初测报告标题口径一致：标题含「复测」为复测报告
                        "is_retest": "复测" in (pr.title or ""),
                        "creator_name": creator_name,
                        "date": rdate,
                    })
            meta["testers"] = testers
            meta["report_records"] = report_records
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
            stamp = now().strftime("%Y%m%d%H%M%S")
            docx_path = str(export_dir / f"report_{report.id}_{stamp}.docx")
            await asyncio.to_thread(build_report_docx, meta, vulns, sections, docx_path, assets)

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
