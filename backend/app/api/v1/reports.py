import html as html_mod
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import VUL_LEVEL, VUL_TYPE
from app.core.deps import require_perm
from app.db import get_session
from app.models import ExportJob, Report, ReportSection, User, Vul
from app.schemas import (
    ExportJobOut,
    Page,
    ReportListOut,
    ReportOut,
    ReportSaveIn,
)
from app.workers.dispatch import dispatch

router = APIRouter(prefix="/reports", tags=["报告"])


def _vuln_section_html(vul: Vul) -> str:
    """由漏洞记录生成标准章节 HTML（供报告编辑器继续编辑）。"""
    info = (
        f"<p><strong>漏洞等级：</strong>{VUL_LEVEL.get(vul.level, '-')}　"
        f"<strong>漏洞类型：</strong>{VUL_TYPE.get(vul.vul_type, '其他')}　"
        f"<strong>影响URL：</strong>{html_mod.escape(vul.affected_url or '-')}</p>"
    )
    parts = [info]
    if vul.description_html:
        parts.append(f"<h3>漏洞描述</h3>{vul.description_html}")
    if vul.reproduce_html:
        parts.append(f"<h3>复现步骤</h3>{vul.reproduce_html}")
    if vul.solution_html:
        parts.append(f"<h3>修复建议</h3>{vul.solution_html}")
    return "".join(parts)


async def _get_report(session: AsyncSession, report_id: int) -> Report:
    report = await session.get(Report, report_id)
    if report is None:
        raise HTTPException(404, "报告不存在")
    return report


@router.get("", response_model=Page[ReportListOut])
async def list_reports(
    search: str = "",
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    _: User = Depends(require_perm("report:manage")),
    session: AsyncSession = Depends(get_session),
):
    cond = []
    if search:
        cond.append(Report.title.ilike(f"%{search}%") | Report.project_name.ilike(f"%{search}%"))
    total = (await session.execute(select(func.count(Report.id)).where(*cond))).scalar_one()
    items = (
        await session.execute(
            select(Report).where(*cond).order_by(Report.update_time.desc())
            .offset((page - 1) * size).limit(size)
        )
    ).scalars().all()
    return Page(total=total, items=items)


@router.post("", response_model=ReportOut)
async def create_report(
    body: ReportSaveIn,
    user: User = Depends(require_perm("report:manage")),
    session: AsyncSession = Depends(get_session),
):
    report = Report(**body.model_dump(exclude={"sections", "version"}), creator_id=user.id)
    for s in body.sections:
        report.sections.append(ReportSection(
            order=s.order, title=s.title,
            content_html=s.content_html, content_json=s.content_json, vul_id=s.vul_id,
        ))
    session.add(report)
    await session.commit()
    await session.refresh(report)
    return report


class FromVulnsIn(BaseModel):
    title: str
    vul_ids: list[int]


@router.post("/from-vulns", response_model=ReportOut)
async def create_report_from_vulns(
    body: FromVulnsIn,
    user: User = Depends(require_perm("report:manage")),
    session: AsyncSession = Depends(get_session),
):
    """从已有漏洞记录一键生成报告草稿，每个漏洞一个章节。"""
    vulns = (await session.execute(select(Vul).where(Vul.id.in_(body.vul_ids)))).scalars().all()
    by_id = {v.id: v for v in vulns}
    report = Report(title=body.title, author=user.realname or user.username, creator_id=user.id)
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
    await session.commit()
    await session.refresh(report)
    return report


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
    _: User = Depends(require_perm("report:manage")),
    session: AsyncSession = Depends(get_session),
):
    """全量保存报告（元信息 + 章节），version 乐观锁防止并发覆盖。"""
    report = await _get_report(session, report_id)
    if body.version != report.version:
        raise HTTPException(409, "报告已被他人修改，请刷新后重试")

    for k, v in body.model_dump(exclude={"sections", "version"}).items():
        setattr(report, k, v)
    report.sections.clear()
    await session.flush()
    for s in body.sections:
        report.sections.append(ReportSection(
            order=s.order, title=s.title,
            content_html=s.content_html, content_json=s.content_json, vul_id=s.vul_id,
        ))
    report.version += 1
    await session.commit()
    await session.refresh(report)
    return report


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
    await _get_report(session, report_id)
    job = ExportJob(report_id=report_id, fmt=body.fmt, creator_id=user.id)
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
    filename = quote(f"{report.title if report else 'report'}.{job.fmt}")
    return FileResponse(
        path,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"},
    )
