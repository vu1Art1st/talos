import html as html_mod
import logging
import re
from datetime import datetime
from io import BytesIO
from pathlib import Path
from urllib.parse import quote
from zipfile import ZipFile

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import ReportStatus, VUL_LEVEL_EXPORT, VulStatus
from app.core.deps import require_perm
from app.core.timeutil import now
from app.core.query import get_or_404, paginate, apply_sort
from app.db import get_session
from app.models import ExportJob, Report, ReportSection, TestingPlan, User, Vul
from app.schemas import (
    ExportCheckIn,
    ExportCheckOut,
    ExportJobOut,
    Page,
    ReportListOut,
    ReportOut,
    ReportSaveIn,
    ReportSimilarityIn,
    ReportSimilarityOut,
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


async def _snapshot_vul_edits(session: AsyncSession, vul_ids: list[int]) -> dict:
    """对所选漏洞生成 {vul_id: update_time} 最后编辑时间快照（key 为字符串）。

    供报告相似性判定使用：生成/保存报告时写入快照，再次生成时对比所选漏洞
    当前的最后编辑时间，全部一致才视为「漏洞内容未变化」。
    """
    ids = [vid for vid in vul_ids if vid]
    if not ids:
        return {}
    rows = (
        await session.execute(select(Vul.id, Vul.update_time).where(Vul.id.in_(ids)))
    ).all()
    return {str(vid): t.isoformat() if t else "" for vid, t in rows}


def _calc_mandays(test_start: str, test_end: str) -> float:
    """实际人天：报告测试结束日期 - 开始日期 + 1（含首尾，最小 1 天）。

    测试周期为 YYYY-MM-DD 字符串；任一缺失、非法或结束早于开始时视为 0。
    报告创建/保存/导出时均自动重算，用户手动修改测试周期后以修改后的时间为准。
    """
    try:
        start = datetime.strptime(test_start, "%Y-%m-%d")
        end = datetime.strptime(test_end, "%Y-%m-%d")
    except (TypeError, ValueError):
        return 0.0
    if end < start:
        return 0.0
    return float((end - start).days + 1)


def _vul_status_snapshot(vulns: list[Vul]) -> dict:
    """关联漏洞状态快照 {vul_id: {status, retest_html, retest_json}}，供复测更新判断。"""
    return {
        str(v.id): {
            "status": v.status,
            "retest_html": v.retest_html or "",
            "retest_json": v.retest_json,
        }
        for v in vulns
    }


def _same_vul_status(prev: dict, current: dict) -> bool:
    """两次复测间漏洞状态与内容是否完全一致（并集比较，任一漏洞新增/移除/状态或内容变化均视为有更新）。"""
    return all(prev.get(k) == v for k, v in current.items()) and all(k in current for k in prev)


async def _report_title_exists(session: AsyncSession, title: str, plan_id: int | None) -> bool:
    """同计划范围内报告标题查重（无计划时按无归属计划口径查重）。"""
    cond = Report.title == title
    if plan_id is not None:
        cond = cond & (Report.testing_plan_id == plan_id)
    else:
        cond = cond & (Report.testing_plan_id.is_(None))
    return (
        await session.execute(select(Report.id).where(cond).limit(1))
    ).scalar_one_or_none() is not None


async def _find_last_retest_report(session: AsyncSession, src: Report) -> Report | None:
    """定位「上一次复测」的报告：源报告自身为复测报告且有快照时优先；
    否则取同计划下最近生成的有状态快照的复测报告（用于判断本次是否重复发起复测）。"""
    if plan_service.is_retest_report_title(src.title) and src.retest_vul_snapshot is not None:
        return src
    if src.testing_plan_id is None:
        return None
    stmt = (
        select(Report)
        .where(
            Report.testing_plan_id == src.testing_plan_id,
            Report.id != src.id,
            Report.retest_vul_snapshot.is_not(None),
        )
        .order_by(Report.id.desc())
        .limit(20)
    )
    for r in (await session.execute(stmt)).scalars().all():
        if plan_service.is_retest_report_title(r.title):
            return r
    return None


async def _create_retest_report(
    session: AsyncSession, src: Report, user: User,
    vul_snapshot: dict | None = None,
) -> Report:
    """基于原报告自动生成复测报告草稿。

    - 标题：当前发起复测日期（YYYYMMDD）为标题前八位，尾部将原「渗透测试报告」替换为「渗透测试复测报告」；
      同一天对同一来源重复发起复测导致标题重复时，自动追加「-1」「-2」后缀规避重名（不再复用旧报告）；
    - 测试周期：开始时间 = 发起复测当天，结束时间 = 生成当天（导出日期默认值，用户可手动修改）；
    - 章节复制原报告（保留漏洞关联），供复测编辑面板逐条处理；
    - 实际人天自动计算 = 结束日期 - 开始日期；
    - retest_vul_snapshot：记录本次发起复测后关联漏洞的状态快照，供下次发起复测时判断是否更新。
    """
    today = now().date()
    # 需求9：先清除原标题开头的旧日期（YYYYMMDD）再拼接当前日期，避免「yyyymmddyyyymmdd+系统名」重复
    base = re.sub(r"^\d{8}", "", src.title).replace("渗透测试报告", "渗透测试复测报告")
    title = f"{today.strftime('%Y%m%d')}{base}"
    suffix = 0
    candidate = title
    while await _report_title_exists(session, candidate, src.testing_plan_id):
        suffix += 1
        candidate = f"{title}-{suffix}"
    report = Report(
        title=candidate,
        project_name=src.project_name,
        customer=src.customer,
        author=user.realname or user.username,
        target_ip=src.target_ip,
        test_start=today.isoformat(),
        test_end=today.isoformat(),
        status="draft",
        testing_plan_id=src.testing_plan_id,
        creator_id=user.id,
        retest_vul_snapshot=vul_snapshot,
    )
    for s in src.sections:
        report.sections.append(ReportSection(
            order=s.order, title=s.title,
            content_html=s.content_html, content_json=s.content_json, vul_id=s.vul_id,
        ))
    session.add(report)
    await session.flush()
    report.actual_mandays = _calc_mandays(report.test_start, report.test_end)
    report.vul_edit_snapshot = await _snapshot_vul_edits(
        session, [s.vul_id for s in report.sections if s.vul_id]
    )
    return report


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
    # 漏洞流转（自动进入修复中）会刷新其最后编辑时间，故快照需在流转后采集
    report.vul_edit_snapshot = await _snapshot_vul_edits(session, linked_ids)
    # 实际人天自动计算：测试结束日期 - 开始日期 + 1
    report.actual_mandays = _calc_mandays(report.test_start, report.test_end)
    # 同步刷新关联测试计划的实际人天（仅纳入初测报告，复测报告不计入）
    await plan_service.refresh_mandays(session, report.testing_plan_id)
    await session.commit()
    await session.refresh(report)
    return report


class FromVulnsIn(BaseModel):
    title: str
    vul_ids: list[int]
    testing_plan_id: int | None = None  # 关联测试计划，联动其状态
    project_name: str = ""  # 系统名称：未显式指定时由关联计划自动填充（导出模板封面第二行）


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
    # 需求8：标题为空时自动生成「yyyymmdd+测试系统名称+渗透测试报告」；
    # 系统名称未显式指定时取关联计划的测试系统名称（导出模板封面第二行展示）
    title = body.title.strip()
    if not title:
        sys_name = plan.system_name if plan is not None else ""
        title = f"{now().date().strftime('%Y%m%d')}{sys_name}渗透测试报告"
    report = Report(
        title=title, author=user.realname or user.username,
        project_name=body.project_name.strip() or (plan.system_name if plan is not None else ""),
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
    # 漏洞流转（自动进入修复中）会刷新其最后编辑时间，故快照需在流转后采集
    report.vul_edit_snapshot = await _snapshot_vul_edits(session, [v.id for v in vulns])
    if plan is not None:
        # 报告已生成，计划进入等待复测阶段
        if vuln_service.can_plan_transition(plan.status, 30):
            plan.status = 30
        if not plan.first_test_done_time:
            plan.first_test_done_time = now().date().isoformat()
    # 实际人天自动计算：测试结束日期 - 开始日期 + 1
    report.actual_mandays = _calc_mandays(report.test_start, report.test_end)
    # 同步刷新关联测试计划的实际人天（仅纳入初测报告，复测报告不计入）
    await plan_service.refresh_mandays(session, report.testing_plan_id)
    await session.commit()
    await session.refresh(report)
    return report


@router.post("/similarity-check", response_model=ReportSimilarityOut)
async def check_report_similarity(
    body: ReportSimilarityIn,
    _: User = Depends(require_perm("report:manage")),
    session: AsyncSession = Depends(get_session),
):
    """再次生成报告前的高度相似性检查。

    对比历史报告的基础信息（标题 + 归属测试计划 + 所选漏洞集合）以及所选漏洞的
    最后编辑时间（生成时的快照），两者完全一致则判定为高度相似，供前端弹窗确认
    是否仍要继续生成。
    """
    vul_ids = sorted({v for v in body.vul_ids if v})
    if not vul_ids:
        return ReportSimilarityOut()
    plan_id = body.testing_plan_id
    if plan_id is None:
        plan_id = await _infer_plan_id(session, vul_ids)
    candidates = (
        await session.execute(
            select(Report)
            .where(Report.title == body.title, Report.testing_plan_id == plan_id)
            .order_by(Report.id.desc())
            .limit(20)
        )
    ).scalars().all()
    current = await _snapshot_vul_edits(session, vul_ids)
    vul_set = set(vul_ids)
    matched: list[Report] = []
    for r in candidates:
        if r.vul_edit_snapshot is not None:
            if r.vul_edit_snapshot == current:
                matched.append(r)
            continue
        # 历史报告（快照缺失，如早于相似性功能上线的存量报告）：
        # 校验关联漏洞集合与当前一致后，回填当前编辑时间快照并判定相似（幂等）。
        # 漏洞的最后编辑时间是绝对值，若生成后未再编辑则回填值即生成时值。
        linked = {s.vul_id for s in r.sections if s.vul_id}
        if linked != vul_set:
            continue
        r.vul_edit_snapshot = current
        matched.append(r)
    if matched:
        await session.commit()
    return ReportSimilarityOut(similar=bool(matched), matched_reports=matched)


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
                "report_id": rid, "job_id": done.id, "status": "done", "fmt": done.fmt, "title": report.title,
                "toc_auto_updated": done.toc_auto_updated,
            })
            continue
        job = ExportJob(
            report_id=rid, title=report.title, fmt=fmt,
            creator_id=user.id, report_snapshot=report.fingerprint(),
        )
        session.add(job)
        await session.flush()
        jobs.append({
            "report_id": rid, "job_id": job.id, "status": job.status, "fmt": job.fmt, "title": report.title,
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
         "fmt": j.fmt, "error": j.error, "title": j.title, "toc_auto_updated": j.toc_auto_updated}
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


def _report_content_changed(report: Report, body: ReportSaveIn) -> bool:
    """报告内容是否发生变更（元信息 + 章节，按 order 排序比较）。

    用于需求6的已定稿报告内容变更检测：内容变化即视为脱离定稿态。
    """
    for k in ("title", "project_name", "customer", "author", "test_start", "test_end", "target_ip"):
        if getattr(report, k) != getattr(body, k):
            return True
    old_sections = [
        (s.title, s.content_html, s.content_json, s.vul_id)
        for s in sorted(report.sections, key=lambda s: s.order)
    ]
    new_sections = [
        (s.title, s.content_html, s.content_json, s.vul_id)
        for s in sorted(body.sections, key=lambda s: s.order)
    ]
    return old_sections != new_sections


@router.put("/{report_id}", response_model=ReportOut)
async def save_report(
    report_id: int,
    body: ReportSaveIn,
    user: User = Depends(require_perm("report:manage")),
    session: AsyncSession = Depends(get_session),
):
    """全量保存报告（元信息 + 章节），revision 乐观锁防止并发覆盖。

    需求6：已定稿(final)报告内容发生变更时，保存后自动回退草稿，需重新导出定稿。
    """
    report = await _get_report(session, report_id)
    if body.revision != report.revision:
        raise HTTPException(409, "报告已被他人修改，请刷新后重试")

    # 需求6：在覆盖前基于旧值判定内容是否变化（纯状态切换不误判）
    content_changed = _report_content_changed(report, body)
    old_plan_id = report.testing_plan_id  # 保存后可能换计划，需分别刷新新旧计划的人天
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
    # 需求6：已定稿报告内容变更后自动回退草稿，需重新导出定稿
    if content_changed and report.status == ReportStatus.FINAL.to_str():
        report.status = ReportStatus.DRAFT.to_str()
    # 编辑中新关联进来的漏洞同样自动进入修复中
    new_linked = [s.vul_id for s in body.sections if s.vul_id and s.vul_id not in old_linked]
    await _auto_mark_fixing(session, new_linked, user, report.title)
    # 快照反映最终状态（新关联漏洞流转会刷新其最后编辑时间），在流转后采集
    report.vul_edit_snapshot = await _snapshot_vul_edits(
        session, [s.vul_id for s in body.sections if s.vul_id]
    )
    # 报告尚未关联计划时，若章节漏洞归属唯一计划则自动回写（不覆盖已有值）
    if report.testing_plan_id is None:
        report.testing_plan_id = await _infer_plan_id(
            session, [s.vul_id for s in body.sections if s.vul_id]
        )
    # 实际人天自动计算：测试结束日期 - 开始日期 + 1（用户手动修改时间后以修改后的时间为准）
    report.actual_mandays = _calc_mandays(report.test_start, report.test_end)
    # 同步刷新关联测试计划的实际人天（仅纳入初测报告，复测报告不计入）
    await plan_service.refresh_mandays(session, report.testing_plan_id)
    if old_plan_id and old_plan_id != report.testing_plan_id:
        await plan_service.refresh_mandays(session, old_plan_id)
    await session.commit()
    await session.refresh(report)
    return report


@router.post("/{report_id}/retest", response_model=ReportOut)
async def retest_report(
    report_id: int,
    user: User = Depends(require_perm("report:manage")),
    session: AsyncSession = Depends(get_session),
):
    """报告列表/测试计划点击「发起复测」：未修复关联漏洞自动流转为复测中，并自动生成复测报告草稿。

    支持从以下状态进入复测：
    - 修复中(50) → 复测中(55)：标准链路
    - 未修复(10) → 复测中(55)：修复状态冗余兜底
    - 复测中(55) → 复测中(55)：已处于复测中则幂等跳过
    - 已修复(60) → 保持已修复不变：发起复测仅对未修复漏洞生效，已闭环漏洞不重新进入复测

    防重复发起复测：再次点击发起复测时对比上一次复测的漏洞状态快照，若漏洞状态与复测内容
    均未变化则阻止生成新报告（返回 400），且不新增复测轮次；有更新才生成新报告进入下一轮。

    复测报告规则：
    - 标题：当前发起复测日期（YYYYMMDD）为标题前八位，尾部将原「渗透测试报告」替换为「渗透测试复测报告」；
      同日多次复测标题重复时自动追加「-1」「-2」后缀；
    - 测试周期：开始时间 = 发起复测时间，结束时间 = 生成当天（导出日期默认值，用户可手动修改）；
    - 实际人天自动计算 = 结束日期 - 开始日期。
    """
    report = await _get_report(session, report_id)
    vul_ids = [s.vul_id for s in report.sections if s.vul_id]
    if not vul_ids:
        raise HTTPException(400, "该报告没有关联任何漏洞，无法发起复测")
    vulns = (await session.execute(select(Vul).where(Vul.id.in_(vul_ids)))).scalars().all()
    # 需求：再次发起复测时对比上一次复测的漏洞状态快照，状态/内容未更新则阻止（不生成新报告、不增加轮次）
    last_retest = await _find_last_retest_report(session, report)
    if last_retest is not None and last_retest.retest_vul_snapshot:
        if _same_vul_status(last_retest.retest_vul_snapshot, _vul_status_snapshot(vulns)):
            raise HTTPException(400, "复测结果未更新，无需生成新的复测报告")
    # 需求：发起复测仅对未修复漏洞生效，已修复(60)漏洞保持原状态，不重新进入复测中
    unfixed_vul_ids = [v.id for v in vulns if v.status != VulStatus.FIXED]
    changed = await vuln_service.auto_transition(
        session, unfixed_vul_ids, 55, user, f"报告《{report.title}》发起复测，自动进入复测中",
    )
    # 对于已处于复测中(55)的漏洞，虽未在 changed 中但同样视为复测流程已发起
    already_retesting = [v for v in vulns if v.status == 55 and v.id not in {c.id for c in changed}]
    effective_changed = bool(changed) or bool(already_retesting)
    # 仅当确有漏洞进入复测时才联动测试计划进入复测中，避免全部漏洞已修复时误流转
    if effective_changed and report.testing_plan_id is not None:
        plan = await session.get(TestingPlan, report.testing_plan_id)
        if plan is not None:
            if vuln_service.can_plan_transition(plan.status, 50):
                plan.status = 50  # 等待复测/复测申请 → 复测中
            plan_service.start_retest_round(
                session, plan, f"报告《{report.title}》发起复测", user.id, force=True,
            )
    # 自动生成复测报告（记录本次发起复测后漏洞状态快照供下次对比；同日标题重复自动加 -1/-2 后缀）
    retest = await _create_retest_report(
        session, report, user, vul_snapshot=_vul_status_snapshot(vulns),
    )
    # 同步刷新关联测试计划的实际人天（复测报告标题含「复测」不计入，值保持不变）
    await plan_service.refresh_mandays(session, report.testing_plan_id)
    await session.commit()
    await session.refresh(retest)
    return retest


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


@router.post("/{report_id}/export-check", response_model=ExportCheckOut)
async def check_export_duplicate(
    report_id: int,
    body: ExportCheckIn,
    _: User = Depends(require_perm("report:manage")),
    session: AsyncSession = Depends(get_session),
):
    """导出前重复判断：报告内容指纹与最近一次同格式成功导出完全一致则判定重复。

    指纹包含报告编辑版本、报告更新时间与关联漏洞编辑时间快照，任一变化即视为内容有变。
    """
    fmt = body.fmt if body.fmt in ("docx", "pdf") else "docx"
    report = await _get_report(session, report_id)
    last = (
        await session.execute(
            select(ExportJob)
            .where(ExportJob.report_id == report_id, ExportJob.fmt == fmt, ExportJob.status == "done")
            .order_by(ExportJob.id.desc()).limit(1)
        )
    ).scalar_one_or_none()
    base = ExportCheckOut(report_id=report_id, report_title=report.title, fmt=fmt)
    if last is None or last.report_snapshot is None:
        return base
    if last.report_snapshot == report.fingerprint():
        file_size: int | None = None
        file_name = ""
        if last.file_path:
            p = Path(last.file_path)
            file_name = p.name
            try:
                file_size = p.stat().st_size
            except OSError:
                file_size = None
        return ExportCheckOut(
            duplicate=True,
            report_id=report_id,
            report_title=report.title,
            fmt=last.fmt,
            last_job_id=last.id,
            last_time=last.finish_time or last.create_time,
            last_status=last.status,
            last_version=report.version,
            last_file_name=file_name,
            last_file_size=file_size,
        )
    return base


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
    # 实际人天自动计算：测试结束日期 - 开始日期 + 1（导出时预填周期同样会刷新该值）
    report.actual_mandays = _calc_mandays(report.test_start, report.test_end)
    # 同步刷新关联测试计划的实际人天（仅纳入初测报告，复测报告不计入）
    await plan_service.refresh_mandays(session, report.testing_plan_id)
    # 预填测试周期会触发报告 update_time（onupdate）刷新，且该值不会回写对象属性，
    # 需 flush + refresh 后采集指纹，确保与最终落库状态一致
    await session.flush()
    await session.refresh(report)
    job = ExportJob(
        report_id=report_id, title=report.title, fmt=body.fmt,
        creator_id=user.id, report_snapshot=report.fingerprint(),
    )
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
