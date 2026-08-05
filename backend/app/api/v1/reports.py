import html as html_mod
import logging
from io import BytesIO
from pathlib import Path
from urllib.parse import quote
from zipfile import ZipFile

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import VUL_LEVEL_EXPORT
from app.core.deps import require_perm
from app.core.timeutil import now
from app.core.query import get_or_404, paginate, apply_sort
from app.db import get_session
from app.models import ExportJob, Report, ReportSection, TestingPlan, User, Vul
from app.schemas import (
    ExportJobOut,
    Page,
    ReportListOut,
    ReportOut,
    ReportSaveIn,
    ReportVulnStateOut,
)
from app.services import plan_service, vuln_service
from app.services.exporter import cleanup_stale_previews, ensure_pdf_preview
from app.workers.dispatch import dispatch

router = APIRouter(prefix="/reports", tags=["报告"])


def _affected_urls_html(affected_url: str | None) -> str:
    """影响 URL 多值以换行分隔存储，逐条转义后换行展示。"""
    urls = [u.strip() for u in (affected_url or "").splitlines() if u.strip()]
    return "<br/>".join(html_mod.escape(u) for u in urls) or "-"


def _vuln_section_html(vul: Vul) -> str:
    """由漏洞记录生成标准章节 HTML，标签结构对齐导出模板「风险问题详情」（供报告编辑器继续编辑）。"""
    parts = [
        f"<p><strong>测试状态：</strong>{'复测' if vul.is_retest else '初测'}</p>",
        f"<p><strong>漏洞等级：</strong>{VUL_LEVEL_EXPORT.get(vul.level, '-')}</p>",
        f"<p><strong>漏洞链接：</strong>{_affected_urls_html(vul.affected_url)}</p>",
    ]
    if vul.description_html:
        parts.append(f"<p><strong>漏洞描述：</strong></p>{vul.description_html}")
    if vul.reproduce_html:
        parts.append(f"<p><strong>漏洞证明：</strong></p>{vul.reproduce_html}")
    if vul.solution_html:
        parts.append(f"<p><strong>修复建议：</strong></p>{vul.solution_html}")
    if vul.retest_html:
        parts.append(f"<p><strong>复测详情：</strong></p>{vul.retest_html}")
    return "".join(parts)


async def _get_report(session: AsyncSession, report_id: int) -> Report:
    return await get_or_404(session, Report, report_id, "报告不存在")


async def _auto_mark_fixing(session: AsyncSession, vul_ids: list[int], user: User, report_title: str) -> None:
    """漏洞关联生成报告后自动流转为「修复中」（仅对处于未修复等可流转状态的漏洞生效）。"""
    await vuln_service.auto_transition(
        session, vul_ids, 50, user, f"关联报告《{report_title}》，自动进入修复中",
    )


async def _infer_plan_id(session: AsyncSession, vul_ids: list[int]) -> int | None:
    """从章节关联漏洞推导归属测试计划：当且仅当这些漏洞归属唯一非空计划时返回该计划 ID。"""
    ids = [vid for vid in vul_ids if vid]
    if not ids:
        return None
    plan_ids = (
        await session.execute(
            select(Vul.testing_plan_id)
            .where(Vul.id.in_(ids), Vul.testing_plan_id.is_not(None))
            .distinct()
        )
    ).scalars().all()
    return plan_ids[0] if len(plan_ids) == 1 else None


@router.get("", response_model=Page[ReportListOut])
async def list_reports(
    search: str = "",
    sort: str = "",
    order: str = "desc",
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    _: User = Depends(require_perm("report:manage")),
    session: AsyncSession = Depends(get_session),
):
    cond = []
    if search:
        cond.append(Report.title.ilike(f"%{search}%") | Report.project_name.ilike(f"%{search}%"))
    stmt = select(Report).where(*cond)
    stmt = apply_sort(
        stmt, Report, sort, order,
        {"id", "title", "project_name", "author", "status", "version", "update_time", "create_time"},
        Report.update_time.desc(),
    )
    total, items = await paginate(session, stmt, page, size)
    return Page(total=total, items=items)


@router.post("", response_model=ReportOut)
async def create_report(
    body: ReportSaveIn,
    user: User = Depends(require_perm("report:manage")),
    session: AsyncSession = Depends(get_session),
):
    report = Report(**body.model_dump(exclude={"sections", "revision"}), creator_id=user.id)
    for s in body.sections:
        report.sections.append(ReportSection(
            order=s.order, title=s.title,
            content_html=s.content_html, content_json=s.content_json, vul_id=s.vul_id,
        ))
    session.add(report)
    await session.flush()
    linked_ids = [s.vul_id for s in body.sections if s.vul_id]
    # 未显式关联计划时，若章节漏洞归属唯一计划则自动回写，保证计划页关联报告数量准确
    if report.testing_plan_id is None:
        report.testing_plan_id = await _infer_plan_id(session, linked_ids)
    await _auto_mark_fixing(session, linked_ids, user, report.title)
    await session.commit()
    await session.refresh(report)
    return report


class FromVulnsIn(BaseModel):
    title: str
    vul_ids: list[int]
    testing_plan_id: int | None = None  # 关联测试计划，联动其状态


@router.post("/from-vulns", response_model=ReportOut)
async def create_report_from_vulns(
    body: FromVulnsIn,
    user: User = Depends(require_perm("report:manage")),
    session: AsyncSession = Depends(get_session),
):
    """从已有漏洞记录一键生成报告草稿，每个漏洞一个章节。"""
    plan = None
    plan_id = body.testing_plan_id
    if plan_id is None:
        # 未显式选择计划时，若所选漏洞归属唯一计划则自动推导
        plan_id = await _infer_plan_id(session, body.vul_ids)
    if plan_id is not None:
        plan = await plan_service.get_plan_or_400(session, plan_id)
    vulns = (await session.execute(select(Vul).where(Vul.id.in_(body.vul_ids)))).scalars().all()
    by_id = {v.id: v for v in vulns}
    report = Report(
        title=body.title, author=user.realname or user.username,
        testing_plan_id=plan_id, creator_id=user.id,
    )
    order = 0
    for vid in body.vul_ids:
        vul = by_id.get(vid)
        if vul is None:
            continue
        report.sections.append(ReportSection(
            order=order, title=vul.title,
            content_html=_vuln_section_html(vul), vul_id=vul.id,
        ))
        order += 1
    session.add(report)
    await session.flush()
    await _auto_mark_fixing(session, [v.id for v in vulns], user, report.title)
    if plan is not None:
        # 报告已生成，计划进入等待复测阶段
        if plan.status in (10, 20):
            plan.status = 30
        if not plan.first_test_done_time:
            plan.first_test_done_time = now().date().isoformat()
    await session.commit()
    await session.refresh(report)
    return report


class BatchExportIn(BaseModel):
    report_ids: list[int]
    fmt: str = "docx"


@router.post("/batch-export")
async def batch_export(
    body: BatchExportIn,
    request: Request,
    user: User = Depends(require_perm("report:manage")),
    session: AsyncSession = Depends(get_session),
):
    """批量导出：复用最近一次成功导出的文件，否则创建导出任务并排队生成。

    返回 [{report_id, job_id, status, title}]，前端据此轮询批量状态后打包下载。"""
    fmt = body.fmt if body.fmt in ("docx", "pdf") else "docx"
    jobs: list[dict] = []
    pending: list[ExportJob] = []
    for rid in body.report_ids:
        report = await session.get(Report, rid)
        if report is None:
            continue
        done = (
            await session.execute(
                select(ExportJob)
                .where(ExportJob.report_id == rid, ExportJob.fmt == fmt, ExportJob.status == "done")
                .order_by(ExportJob.id.desc()).limit(1)
            )
        ).scalar_one_or_none()
        if done is not None and done.file_path and Path(done.file_path).exists():
            jobs.append({
                "report_id": rid, "job_id": done.id, "status": "done", "title": report.title,
                "toc_auto_updated": done.toc_auto_updated,
            })
            continue
        job = ExportJob(report_id=rid, title=report.title, fmt=fmt, creator_id=user.id)
        session.add(job)
        await session.flush()
        jobs.append({
            "report_id": rid, "job_id": job.id, "status": job.status, "title": report.title,
            "toc_auto_updated": job.toc_auto_updated,
        })
        pending.append(job)
    await session.commit()
    for job in pending:
        await dispatch(request.app, "export_report_task", job.id)
    return jobs


@router.get("/export-jobs/status")
async def export_jobs_status(
    job_ids: str = "",
    _: User = Depends(require_perm("report:manage")),
    session: AsyncSession = Depends(get_session),
):
    """批量轮询导出任务状态（job_ids 逗号分隔）。"""
    ids = [int(x) for x in job_ids.split(",") if x.strip().isdigit()]
    if not ids:
        return []
    rows = (
        await session.execute(select(ExportJob).where(ExportJob.id.in_(ids)))
    ).scalars().all()
    return [
        {"job_id": j.id, "report_id": j.report_id, "status": j.status,
         "error": j.error, "title": j.title, "toc_auto_updated": j.toc_auto_updated}
        for j in rows
    ]


@router.get("/batch-download")
async def batch_download(
    job_ids: str = "",
    _: User = Depends(require_perm("report:manage")),
    session: AsyncSession = Depends(get_session),
):
    """将勾选报告已完成的导出文件打包为 zip 下载。"""
    ids = [int(x) for x in job_ids.split(",") if x.strip().isdigit()]
    if not ids:
        raise HTTPException(400, "未选择导出任务")
    rows = (
        await session.execute(
            select(ExportJob).where(ExportJob.id.in_(ids), ExportJob.status == "done")
        )
    ).scalars().all()
    files = [(Path(j.file_path), j) for j in rows if j.file_path and Path(j.file_path).exists()]
    if not files:
        raise HTTPException(404, "暂无可下载的导出文件，请等待导出完成后再试")
    buf = BytesIO()
    with ZipFile(buf, "w") as zf:
        for path, job in files:
            report = await session.get(Report, job.report_id)
            name = f"{job.title or (report.title if report else 'report')}.{job.fmt}"
            zf.write(path, name)
    buf.seek(0)
    filename = quote("测试报告批量下载.zip")
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"},
    )


@router.get("/{report_id}", response_model=ReportOut)
async def get_report(
    report_id: int,
    _: User = Depends(require_perm("report:manage")),
    session: AsyncSession = Depends(get_session),
):
    return await _get_report(session, report_id)


@router.put("/{report_id}", response_model=ReportOut)
async def save_report(
    report_id: int,
    body: ReportSaveIn,
    user: User = Depends(require_perm("report:manage")),
    session: AsyncSession = Depends(get_session),
):
    """全量保存报告（元信息 + 章节），revision 乐观锁防止并发覆盖。"""
    report = await _get_report(session, report_id)
    if body.revision != report.revision:
        raise HTTPException(409, "报告已被他人修改，请刷新后重试")

    old_linked = {s.vul_id for s in report.sections if s.vul_id}
    for k, v in body.model_dump(exclude={"sections", "revision"}).items():
        setattr(report, k, v)
    report.sections.clear()
    await session.flush()
    for s in body.sections:
        report.sections.append(ReportSection(
            order=s.order, title=s.title,
            content_html=s.content_html, content_json=s.content_json, vul_id=s.vul_id,
        ))
    report.revision += 1
    # 编辑中新关联进来的漏洞同样自动进入修复中
    new_linked = [s.vul_id for s in body.sections if s.vul_id and s.vul_id not in old_linked]
    await _auto_mark_fixing(session, new_linked, user, report.title)
    # 报告尚未关联计划时，若章节漏洞归属唯一计划则自动回写（不覆盖已有值）
    if report.testing_plan_id is None:
        report.testing_plan_id = await _infer_plan_id(
            session, [s.vul_id for s in body.sections if s.vul_id]
        )
    await session.commit()
    await session.refresh(report)
    return report


@router.post("/{report_id}/retest", response_model=ReportOut)
async def retest_report(
    report_id: int,
    user: User = Depends(require_perm("report:manage")),
    session: AsyncSession = Depends(get_session),
):
    """报告列表点击「复测」：关联漏洞由修复中自动流转为复测中，随后进入复测报告编辑。"""
    report = await _get_report(session, report_id)
    vul_ids = [s.vul_id for s in report.sections if s.vul_id]
    if not vul_ids:
        raise HTTPException(400, "该报告没有关联任何漏洞，无法发起复测")
    changed = await vuln_service.auto_transition(
        session, vul_ids, 55, user, f"报告《{report.title}》发起复测，自动进入复测中",
    )
    if report.testing_plan_id is not None:
        plan = await session.get(TestingPlan, report.testing_plan_id)
        if plan is not None:
            if plan.status in (30, 40):
                plan.status = 50  # 等待复测/复测申请 → 复测中
            # 实际有漏洞进入复测时记一轮复测（重复点击不产生流转则不计数）
            if changed:
                plan_service.start_retest_round(
                    session, plan, f"报告《{report.title}》发起复测", user.id, force=True,
                )
    await session.commit()
    await session.refresh(report)
    return report


@router.get("/{report_id}/vuln-states", response_model=list[ReportVulnStateOut])
async def report_vuln_states(
    report_id: int,
    _: User = Depends(require_perm("report:manage")),
    session: AsyncSession = Depends(get_session),
):
    """报告关联漏洞的状态与复测详情，供复测编辑面板渲染。"""
    report = await _get_report(session, report_id)
    vul_ids = [s.vul_id for s in report.sections if s.vul_id]
    if not vul_ids:
        return []
    vulns = (await session.execute(select(Vul).where(Vul.id.in_(vul_ids)))).scalars().all()
    by_id = {v.id: v for v in vulns}
    return [
        ReportVulnStateOut(
            vul_id=v.id, title=v.title, status=v.status, level=v.level,
            vul_type=v.vul_type, layer=v.layer,
            retest_html=v.retest_html, retest_json=v.retest_json,
        )
        for vid in vul_ids if (v := by_id.get(vid))
    ]


@router.delete("/{report_id}")
async def delete_report(
    report_id: int,
    _: User = Depends(require_perm("report:manage")),
    session: AsyncSession = Depends(get_session),
):
    report = await session.get(Report, report_id)
    if report:
        await session.execute(
            ExportJob.__table__.delete().where(ExportJob.report_id == report_id)
        )
        await session.delete(report)
        await session.commit()
    return {"msg": "删除成功"}


class ExportIn(BaseModel):
    fmt: str = "docx"


@router.post("/{report_id}/export", response_model=ExportJobOut)
async def export_report(
    report_id: int,
    body: ExportIn,
    request: Request,
    user: User = Depends(require_perm("report:manage")),
    session: AsyncSession = Depends(get_session),
):
    if body.fmt not in ("docx", "pdf"):
        raise HTTPException(400, "仅支持导出 docx 或 pdf")
    report = await _get_report(session, report_id)
    # 测试周期自动预填（仅当字段为空，不覆盖用户已填写值）：
    # 开始日期 = 关联漏洞最早提交日期，结束日期 = 当天
    if not report.test_start or not report.test_end:
        vul_ids = [s.vul_id for s in report.sections if s.vul_id]
        if not report.test_start and vul_ids:
            earliest = (
                await session.execute(
                    select(func.min(Vul.submit_time)).where(Vul.id.in_(vul_ids))
                )
            ).scalar_one_or_none()
            if earliest is not None:
                report.test_start = earliest.date().isoformat()
        if not report.test_end:
            report.test_end = now().date().isoformat()
    job = ExportJob(report_id=report_id, title=report.title, fmt=body.fmt, creator_id=user.id)
    session.add(job)
    await session.commit()
    await session.refresh(job)
    await dispatch(request.app, "export_report_task", job.id)
    return job


@router.get("/{report_id}/exports", response_model=list[ExportJobOut])
async def list_export_jobs(
    report_id: int,
    _: User = Depends(require_perm("report:manage")),
    session: AsyncSession = Depends(get_session),
):
    jobs = (
        await session.execute(
            select(ExportJob).where(ExportJob.report_id == report_id)
            .order_by(ExportJob.id.desc()).limit(20)
        )
    ).scalars().all()
    return jobs


@router.get("/exports/{job_id}/download")
async def download_export(
    job_id: int,
    _: User = Depends(require_perm("report:manage")),
    session: AsyncSession = Depends(get_session),
):
    job = await session.get(ExportJob, job_id)
    if job is None or job.status != "done":
        raise HTTPException(404, "导出文件不存在或尚未生成完成")
    path = Path(job.file_path)
    if not path.exists():
        raise HTTPException(404, "导出文件已被清理")
    report = await session.get(Report, job.report_id)
    filename = quote(f"{job.title or (report.title if report else 'report')}.{job.fmt}")
    return FileResponse(
        path,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"},
    )


@router.get("/exports/{job_id}/preview")
async def preview_export(
    job_id: int,
    _: User = Depends(require_perm("report:manage")),
    session: AsyncSession = Depends(get_session),
):
    """在线预览导出文件：pdf 直接返回，docx 临时转为 PDF 展示。"""
    job = await session.get(ExportJob, job_id)
    if job is None or job.status != "done":
        raise HTTPException(404, "导出文件不存在或尚未生成完成")
    path = Path(job.file_path)
    if not path.exists():
        raise HTTPException(404, "导出文件已被清理")
    cleanup_stale_previews()  # 顺带清理过期预览
    try:
        pdf_path = await ensure_pdf_preview(str(path))
    except Exception:
        logging.getLogger(__name__).exception("预览转换失败 job_id=%s", job_id)
        raise HTTPException(502, "预览转换失败，请稍后重试或联系管理员")
    report = await session.get(Report, job.report_id)
    filename = quote(f"{job.title or (report.title if report else 'report')}.pdf")
    return FileResponse(
        pdf_path,
        media_type="application/pdf",
        headers={"Content-Disposition": f"inline; filename*=UTF-8''{filename}"},
    )


@router.delete("/exports/{job_id}")
async def delete_export(
    job_id: int,
    _: User = Depends(require_perm("report:manage")),
    session: AsyncSession = Depends(get_session),
):
    """删除导出记录及其生成的报告文件。"""
    job = await session.get(ExportJob, job_id)
    if job is None:
        raise HTTPException(404, "导出记录不存在")
    if job.status in ("pending", "running"):
        raise HTTPException(400, "导出任务进行中，请稍后再删除")
    if job.file_path:
        Path(job.file_path).unlink(missing_ok=True)
    await session.delete(job)
    await session.commit()
    return {"msg": "删除成功"}
