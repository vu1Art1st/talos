"""报告导出元数据构建：手动导出（arq worker）与导入后自动导出共用的唯一实现。

背景（2026-09-17 审计 B-1）：`services/import_service.auto_export_report` 与
`workers/main.export_report_task` 曾各自实现同一段 meta / 版本记录 / 章节 / 漏洞 / 资产构建
逻辑（约 110 行），并已产生口径分叉：

1. 版本变更记录日期：「当前报告」分支是否回退到 `report.create_time`；
2. `meta.report_time`（封面与版本记录的时间基准）：导入路径注入、手动导出路径不注入，
   而 `report_builder.build_report_docx` 以 `meta.report_time or tznow()` 取值，
   即「导入报告=标题日期、手动导出=当前时间」是有意设计。

因此本模块把差异收敛为**显式参数**（`report_time`、`generator`），其余逻辑单一实现，
避免再次分叉。
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutil import now
from app.models import ExportJob, Report, TestingPlan, User, Vul
from app.services.plan_service import is_retest_report_title


def collect_testers(plan: TestingPlan | None) -> list[str]:
    """工单参测人员姓名（按 realname > username 取值，去重保序）。"""
    testers: list[str] = []
    if plan is None:
        return testers
    for u in plan.testers:
        name = (u.realname or u.username or "").strip()
        if name and name not in testers:
            testers.append(name)
    return testers


def collect_plan_urls(plan: TestingPlan | None) -> list[str]:
    """工单「被测系统URL」：测试目标表的优先数据源，为空时由调用方回退资产聚合。"""
    if plan is None:
        return []
    return [u for u in (plan.target_urls or []) if u]


async def resolve_plan(session: AsyncSession, report: Report) -> TestingPlan | None:
    """按报告关联的工单 ID 取工单（手动导出路径需要自行解析）。"""
    if report.testing_plan_id is None:
        return None
    return await session.get(TestingPlan, report.testing_plan_id)


async def collect_report_records(
    session: AsyncSession, plan: TestingPlan, current_report_id: int
) -> list[dict]:
    """版本变更记录的「报告 → 日期」序列（报告是版本号唯一数据源）。

    日期口径（统一后）：
    - 当前报告：最近一次成功导出时间 > 报告自身日期（导入报告=标题日期）> 导出当天；
    - 其他报告：最近一次成功导出时间 > 报告自身日期 > 空。
    """
    plan_reports = (
        await session.execute(
            select(Report)
            .where(Report.testing_plan_id == plan.id)
            .order_by(Report.create_time, Report.id)
        )
    ).scalars().all()

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
    records: list[dict] = []
    for pr in plan_reports:
        created = pr.create_time.strftime("%Y-%m-%d") if pr.create_time is not None else ""
        if pr.id == current_report_id:
            # 当前报告：优先最近成功导出时间；无则取报告自身日期（导入报告=标题日期 14:00），
            # 保证版本记录显示报告日期而非本次导出时间
            rdate = last_done.get(pr.id) or created or export_date_str
        else:
            rdate = last_done.get(pr.id) or created
        creator_name = ""
        if pr.creator_id is not None:
            cu = await session.get(User, pr.creator_id)
            if cu is not None:
                creator_name = cu.realname or cu.username or ""
        if not creator_name:
            creator_name = pr.author or ""
        records.append({
            # 复测判定口径唯一来源：plan_service.is_retest_report_title（标题含「复测」）
            "is_retest": is_retest_report_title(pr.title),
            "creator_name": creator_name,
            "date": rdate,
        })
    return records


async def build_export_meta(
    session: AsyncSession,
    report: Report,
    *,
    plan: TestingPlan | None = None,
    generator: str | None = None,
    report_time: datetime | None = None,
) -> dict:
    """构建导出 meta。

    - `generator`：发起导出的账号名（版本变更记录「修改人」列）；None 表示不注入该键；
    - `report_time`：封面与版本记录的时间基准；None 表示交由 `report_builder` 取当前时间
      （手动导出口径），非 None 用于导入自动导出（取报告 create_time = 标题日期）。
    """
    meta: dict = {
        "title": report.title,
        "project_name": report.project_name,
        "customer": report.customer,
        "author": report.author,
        "test_start": report.test_start,
        "test_end": report.test_end,
        "target_ip": report.target_ip,
        "test_account": report.test_account,
        "is_retest": is_retest_report_title(report.title),
    }
    if report_time is not None:
        meta["report_time"] = report_time
    if generator is not None:
        meta["generator"] = generator
    meta["testers"] = collect_testers(plan)
    meta["report_records"] = (
        await collect_report_records(session, plan, report.id) if plan is not None else []
    )
    return meta


def build_sections(report: Report) -> list[dict]:
    """章节快照（复测详情不在此内嵌，唯一权威源仍是 vulns.retest_html）。"""
    return [
        {"title": s.title, "content_html": s.content_html, "vul_id": s.vul_id}
        for s in report.sections
    ]


async def collect_vulns_and_assets(
    session: AsyncSession, sections: list[dict]
) -> tuple[list[dict], list[dict]]:
    """章节涉及的漏洞明细与去重后的关联资产（供模板漏洞详情框与测试目标表使用）。"""
    vul_ids = [s["vul_id"] for s in sections if s["vul_id"]]
    if not vul_ids:
        return [], []
    rows = (await session.execute(select(Vul).where(Vul.id.in_(vul_ids)))).scalars().all()
    by_id = {v.id: v for v in rows}
    vulns = [
        {
            "id": v.id, "title": v.title, "vul_type": v.vul_type, "level": v.level,
            "status": v.status, "affected_url": v.affected_url, "is_retest": v.is_retest,
            "retest_html": v.retest_html,
        }
        for vid in vul_ids if (v := by_id.get(vid))
    ]
    assets: list[dict] = []
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
    return vulns, assets
