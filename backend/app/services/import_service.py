"""Word 导入确认入库：解析校验、报告批次编排、知识库回填、去重合并与收尾。

路由层（api/v1/imports.py::confirm_batch）只做参数编排与消息汇总，
本模块按「解析校验 → 报告编排 → 知识库回填 → 去重合并/建漏洞 → 收尾」承接全部业务逻辑。
事务统一由路由层 commit，本模块只做 flush（保证自增 ID 可用）。
"""
import asyncio
import ipaddress
import re
from datetime import datetime as _dt, time as _dt_time
from urllib.parse import urlparse

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.timeutil import mandays_between, now
from app.models import (
    Asset,
    ExportJob,
    ImportBatch,
    ImportRecord,
    KnowledgeEntry,
    Report,
    ReportSection,
    TestingPlan,
    User,
    Vul,
    VulLog,
)
from app.services import plan_service, vuln_service
from app.services.report_builder import build_report_docx
from app.services.report_html import vuln_section_html


async def load_parsed_records(
    session: AsyncSession, batch_id: int, record_ids: list[int]
) -> list[ImportRecord]:
    """加载本次待入库的解析成功记录，无可入库记录直接 400。"""
    records = (
        await session.execute(
            select(ImportRecord).where(
                ImportRecord.batch_id == batch_id,
                ImportRecord.id.in_(record_ids),
                ImportRecord.status == "parsed",
            )
        )
    ).scalars().all()
    if not records:
        raise HTTPException(400, "没有可入库的记录（仅解析成功且未入库的记录可确认）")
    return list(records)


async def sync_plan_testers(session: AsyncSession, plan: TestingPlan, testers: list[str]) -> None:
    """把导入报告的参测人员（姓名）映射为系统账号并关联到工单测试人员。

    匹配优先级：真实姓名 realname → 用户名 username；未命中的姓名忽略（保留原文，
    不影响报告作者拼接，仅无法关联工单认领）。已关联的账号按 id 去重保留。
    """
    names = [t.strip() for t in (testers or []) if (t or "").strip()]
    if not names:
        return
    users = (
        await session.execute(
            select(User).where(or_(User.realname.in_(names), User.username.in_(names)))
        )
    ).scalars().all()
    if not users:
        return
    existing_ids = {u.id for u in plan.testers}
    new_users = [u for u in users if u.id not in existing_ids]
    if new_users:
        plan.testers.extend(new_users)


async def resolve_report_plan(
    session: AsyncSession, batch: ImportBatch, user: User,
    plan: TestingPlan | None, is_retest: bool, all_fixed: bool,
) -> tuple[TestingPlan | None, object | None]:
    """报告格式批次的计划编排：未显式指定计划时按系统名自动匹配/创建，
    再按「初测 / 复测全修复 / 复测未全修复」置计划状态并维护复测轮次。

    返回 (计划, 本轮复测轮次)；无系统名且未指定计划时返回 (None, None)，
    此时后续的资产补建与自动报告均不执行（与既有行为一致）。
    """
    batch_meta = batch.meta_json or {}
    system_name = (batch_meta.get("system_name") or "").strip()
    if plan is None:
        # 未显式指定计划：按系统名自动匹配，不存在则创建
        if system_name:
            plan = (
                await session.execute(
                    select(TestingPlan).where(TestingPlan.system_name == system_name)
                )
            ).scalars().first()
            if plan is None:
                plan = TestingPlan(system_name=system_name, test_type="渗透测试", creator_id=user.id)
                session.add(plan)
    if plan is None:
        return None, None

    await session.flush()  # 确保 plan.id 可用于复测轮次与报告关联
    # 惰性关系（复测轮次/测试人员）新建计划需显式加载后才能在同步逻辑中访问，否则触发同步 lazy load 抛 MissingGreenlet
    await session.refresh(plan, attribute_names=["retest_rounds", "testers"])
    # 参测人员（docx 时间与人员表）→ 系统账号映射，关联为工单测试人员
    await sync_plan_testers(session, plan, batch_meta.get("testers") or [])
    report_date = batch_meta.get("report_date") or ""
    round_row = None
    if is_retest:
        # 每份复测报告代表一轮复测：无论修复与否统一建轮（force 会把上一轮未闭环轮次打点后再开新一轮），
        # 全部修复才打完成点并置复测完成；否则停留在复测中待后续复测报告闭环
        round_row = plan_service.start_retest_round(session, plan, "报告导入复测", user.id, force=True)
        if all_fixed:
            plan.status = 60  # 复测完成
            plan.retest_done_time = report_date or plan.retest_done_time
            plan_service.finish_retest_round(plan)
        else:
            plan.status = 50  # 复测中：仍有未修复漏洞待闭环
    else:
        plan.status = 30  # 初测完成，等待复测
        plan.first_test_done_time = report_date or plan.first_test_done_time
    return plan, round_row


def _split_urls(raw: str) -> list[str]:
    """拆分被测系统URL字段：按换行 / 分号 / 逗号 / 空白分隔为多条 URL。"""
    parts = re.split(r"[\n\r;；,，\s]+", raw or "")
    return [p.strip() for p in parts if p.strip()]


def _is_internal_url(url: str) -> bool:
    """内网判定：主机为内网 / 回环 / 链路本地地址；域名（无法解析为 IP）视为公网。"""
    host = urlparse(url if "://" in url else f"http://{url}").hostname
    if not host:
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return ip.is_private or ip.is_loopback or ip.is_link_local


async def resolve_report_asset(
    session: AsyncSession, batch: ImportBatch, plan: TestingPlan, asset: Asset | None,
) -> Asset | None:
    """报告格式批次的资产编排：按系统名匹配/自动创建（补被测 URL/IP），
    无系统名但计划已关联资产时默认入库到首个关联资产；
    所有路径都会把被测系统 URL 去重合并进资产 internal_urls；最后把资产关联到计划。"""
    batch_meta = batch.meta_json or {}
    system_name = (batch_meta.get("system_name") or "").strip()
    if asset is None:
        if system_name:
            asset = (
                await session.execute(select(Asset).where(Asset.name == system_name))
            ).scalars().first()
            target_ip = (batch_meta.get("target_ip") or "").strip()
            if asset is None:
                remark = "导入报告自动创建"
                if target_ip:
                    remark += f"；被测IP：{target_ip}"
                asset = Asset(name=system_name, remark=remark)
                session.add(asset)
            await session.flush()
        elif plan.asset_ids:
            # 无系统名但计划已关联资产时，默认入库到首个关联资产
            asset = await session.get(Asset, plan.asset_ids[0])
    # 被测系统 URL 自动更新到资产（拆分多条、按公网/内网分类去重）；显式指定资产时同样生效。
    # 公网域名/公网IP → public_urls（tag=10 互联网）；内网 IP → internal_urls
    if asset is not None:
        for u in _split_urls(batch_meta.get("target_url") or ""):
            if _is_internal_url(u):
                urls = list(asset.internal_urls or [])
                if u not in urls:
                    urls.append(u)
                    asset.internal_urls = urls
            else:
                publics = list(asset.public_urls or [])
                seen = {p.get("url") for p in publics if isinstance(p, dict)}
                if u not in seen:
                    publics.append({"url": u, "tag": 10})  # URL_TAG 10=互联网
                    asset.public_urls = publics
        # 本次入库的资产自动关联到计划，保持「资产关联前置至计划」的一致性
        plan_asset_ids = list(plan.asset_ids or [])
        if asset.id not in plan_asset_ids:
            plan_asset_ids.append(asset.id)
            plan.asset_ids = plan_asset_ids
    return asset


async def ensure_report_and_bind_round(
    session: AsyncSession, batch: ImportBatch, plan: TestingPlan, user: User,
    report: Report | None, round_row,
) -> tuple[Report | None, bool]:
    """报告格式批次的报告编排：未显式指定报告时自动创建草稿报告（使导入报告显示在
    报告中心并支持复测信息编辑），并把本轮复测轮次关联到报告——删除报告时据此回退轮次，
    保持复测轮数与报告一致。返回 (报告, 是否自动创建)。"""
    batch_meta = batch.meta_json or {}
    auto_created = False
    if report is None:
        # 参测人员优先取 docx「时间与人员」表（meta.testers），无则回退工单测试人员姓名；
        # 与前端报告编辑多选逻辑「、」拼接一致
        meta_testers = [t for t in (batch_meta.get("testers") or []) if (t or "").strip()]
        author = "、".join(meta_testers) if meta_testers else (
            "、".join(t.realname or t.username for t in plan.testers) if plan.testers else ""
        )
        # 报告时间取报告标题日期（report_date），小时固定 14:00；无有效日期时由 DB default 落当前时间
        create_time = None
        report_date = (batch_meta.get("report_date") or "").strip()
        if report_date:
            try:
                create_time = _dt.combine(_dt.strptime(report_date, "%Y-%m-%d").date(), _dt_time(14, 0))
            except ValueError:
                create_time = None
        test_start = (batch_meta.get("test_start") or "").strip()
        test_end = (batch_meta.get("test_end") or "").strip()
        report_kwargs = {"create_time": create_time} if create_time is not None else {}
        report = Report(
            title=batch.filename.rsplit(".", 1)[0],
            project_name=(batch_meta.get("system_name") or "").strip() or plan.system_name,
            target_ip=(batch_meta.get("target_ip") or ""),
            test_account=(batch_meta.get("test_account") or "").strip(),
            testing_plan_id=plan.id,
            author=author,
            test_start=test_start,
            test_end=test_end,
            actual_mandays=mandays_between(test_start, test_end),
            creator_id=user.id,
            status="draft",  # 需求6：新生成报告一律为草稿，定稿由导出 Word 驱动
            **report_kwargs,
        )
        session.add(report)
        await session.flush()
        await session.refresh(report, attribute_names=["sections"])
        auto_created = True
    if round_row is not None:
        round_row.report_id = report.id
    return report, auto_created


async def load_knowledge_map(session: AsyncSession, records: list[ImportRecord]) -> dict[int, KnowledgeEntry]:
    """知识库回填映射：按漏洞类型取等级最高、id 最小的一条（与 /knowledge/by-type 语义一致）。"""
    kb_types = {rec.vul_type for rec in records}
    kb_map: dict[int, KnowledgeEntry] = {}
    for e in (
        await session.execute(
            select(KnowledgeEntry)
            .where(KnowledgeEntry.vul_type.in_(kb_types))
            .order_by(KnowledgeEntry.severity_level.desc(), KnowledgeEntry.id.desc())
        )
    ).scalars().all():
        kb_map[e.vul_type] = e  # 降序遍历，最后覆盖的即为等级最高、id 最小的一条
    return kb_map


def apply_knowledge_backfill(rec: ImportRecord, kb: KnowledgeEntry | None) -> tuple[str, str]:
    """解析内容为空的描述/修复建议自动套用对应漏洞类型模板（含危害说明拼接）。"""
    description_html = rec.description_html
    solution_html = rec.solution_html
    if kb is not None:
        if not (description_html or "").strip() and kb.description_html:
            description_html = kb.description_html
            if kb.harm_html:
                description_html += f"<p><strong>危害说明：</strong></p>{kb.harm_html}"
        if not (solution_html or "").strip() and kb.solution_html:
            solution_html = kb.solution_html
    return description_html, solution_html


async def find_existing_report_vul(
    session: AsyncSession, plan: TestingPlan, doc_kind: str, title: str,
) -> Vul | None:
    """报告格式批次去重：同工单 + 同漏洞标题视为同一漏洞，返回既有记录（无则新建）。"""
    if doc_kind != "report":
        return None
    return (
        await session.execute(
            select(Vul)
            .where(Vul.testing_plan_id == plan.id, Vul.title == title)
            .order_by(Vul.id.desc()).limit(1)
        )
    ).scalar_one_or_none()


def update_vul_from_retest(
    vul: Vul, rec: ImportRecord,
    description_html: str, solution_html: str, is_retest: bool,
) -> Vul:
    """复测报告更新既有漏洞：仅覆盖本轮报告携带的信息，保留初测提交时间等不变。"""
    vul.level = rec.level
    vul.vul_type = rec.vul_type
    if rec.affected_url:
        vul.affected_url = rec.affected_url
    if description_html:
        vul.description_html = description_html
    if rec.reproduce_html:
        vul.reproduce_html = rec.reproduce_html
    if solution_html:
        vul.solution_html = solution_html
    if rec.retest_html:
        vul.retest_html = rec.retest_html
    if is_retest:
        vul.is_retest = True
        if rec.fixed:
            vul.status = 60  # 复测报告标记已修复
            vul.fix_time = now()
        else:
            vul.status = 50  # 复测未修复：修复中 + is_retest，展示层为「复测未修复/复测未通过」
    return vul


def create_vul_from_record(
    rec: ImportRecord, batch: ImportBatch, plan: TestingPlan | None, asset: Asset | None,
    user: User, description_html: str, solution_html: str, is_retest: bool,
) -> Vul:
    """由解析记录新建漏洞：来源固定为「渗透测试工单」（source=0 展示层派生），
    关联计划/资产并按报告口径设置复测标记与状态。"""
    batch_meta = batch.meta_json or {}
    vul = Vul(
        title=rec.title,
        vul_type=rec.vul_type,
        level=rec.level,
        affected_url=rec.affected_url,
        description_html=description_html,
        reproduce_html=rec.reproduce_html,
        solution_html=solution_html,
        source=0,  # 来源未选择（Word导入不再单列，关联工单时展示为「渗透测试工单」）
        submitter_id=user.id,
    )
    # 显式指定或报告格式自动匹配的测试计划：任何文档格式均关联漏洞
    if plan is not None:
        vul.testing_plan_id = plan.id
    if batch.doc_kind == "report":
        vul.is_retest = bool(batch_meta.get("is_retest"))
        vul.retest_html = rec.retest_html
        if rec.fixed:
            vul.status = 60  # 报告中标记已修复
            vul.fix_time = now()
        elif is_retest:
            vul.status = 50  # 复测未修复：修复中 + is_retest，展示层为「复测未修复/复测未通过」
    if asset is not None:
        vul.assets = [asset]
    return vul


async def confirm_one_record(
    session: AsyncSession, batch: ImportBatch, rec: ImportRecord,
    plan: TestingPlan | None, asset: Asset | None, report: Report | None,
    user: User, kb_map: dict[int, KnowledgeEntry], is_retest: bool, created: int,
) -> tuple[Vul, bool]:
    """确认单条解析记录：知识库回填 → 去重合并/新建漏洞 → 写日志 → 关联报告章节。

    返回 (漏洞, 是否新建)；created 为已处理的记录条数，用于报告章节排序。
    """
    description_html, solution_html = apply_knowledge_backfill(rec, kb_map.get(rec.vul_type))
    existing = (
        await find_existing_report_vul(session, plan, batch.doc_kind, rec.title)
        if plan is not None else None
    )
    if existing is not None:
        vul = update_vul_from_retest(existing, rec, description_html, solution_html, is_retest)
        is_new = False
    else:
        vul = create_vul_from_record(rec, batch, plan, asset, user, description_html, solution_html, is_retest)
        session.add(vul)
        await session.flush()
        is_new = True
    session.add(VulLog(
        vul_id=vul.id, user_id=user.id, username=user.username,
        action="Word导入创建" if is_new else "Word导入复测更新",
        content=f"来源批次 #{batch.id}（{batch.filename}）",
    ))
    rec.status = "confirmed"
    rec.vul_id = vul.id
    # 关联到指定报告：自动追加为漏洞章节
    if report is not None:
        session.add(ReportSection(
            report_id=report.id,
            order=len(report.sections) + created,
            title=vul.title,
            content_html=vuln_section_html(vul),
            vul_id=vul.id,
        ))
    return vul, is_new


async def finalize_confirm(
    session: AsyncSession, batch: ImportBatch, plan: TestingPlan | None,
    report: Report | None, report_auto_created: bool,
    new_vul_ids: list[int], user: User,
) -> None:
    """入库收尾：既有报告追加章节后自增编辑锁并把新漏洞推入修复中，
    重算计划统计，全部记录处理完则批次置为已确认。"""
    if report is not None and not report_auto_created:
        report.revision += 1  # 追加章节属编辑操作，仅自增编辑锁；导出版本号只在导出成功时 +1
        # 与报告编辑关联漏洞的行为一致：自动进入修复中
        await vuln_service.auto_transition(
            session, new_vul_ids, 50, user, f"关联报告《{report.title}》，自动进入修复中",
        )
    if plan is not None:
        await plan_service.refresh_stats(session, plan.id)
    remaining = (
        await session.execute(
            select(func.count(ImportRecord.id)).where(
                ImportRecord.batch_id == batch.id,
                ImportRecord.status.in_(["parsed", "error"]),
            )
        )
    ).scalar_one()
    if remaining == 0:
        batch.status = "confirmed"


async def auto_export_report(
    session: AsyncSession, report: Report, plan: TestingPlan | None,
    user: User, auto_time: _dt | None,
) -> None:
    """导入报告确认入库后自动生成 docx 文件并记录导出任务（可下载）。

    构建 meta 与后台导出任务口径一致（版本变更记录 / 参测人员 / 测试账号等），
    时间取报告标题日期固定 14:00；文件同步生成，不依赖 arq 队列（开发免队列也生效）。
    导入新报告无实际改动，导出成功不会改变报告指纹以外的内容，仅导出版本号 +1。
    """
    meta = {
        "title": report.title,
        "project_name": report.project_name,
        "customer": report.customer,
        "author": report.author,
        "test_start": report.test_start,
        "test_end": report.test_end,
        "target_ip": report.target_ip,
        "test_account": report.test_account,
        "status": report.status,
        "is_retest": "复测" in (report.title or ""),
        # 报告时间（导入报告=标题日期 14:00）：封面日期与版本变更记录均以它为基准，而非当前时间
        "report_time": report.create_time,
    }
    if user is not None:
        meta["generator"] = user.realname or user.username or ""
    testers: list[str] = []
    report_records: list[dict] = []
    plan_urls: list[str] = []
    if plan is not None:
        for u in plan.testers:
            name = (u.realname or u.username or "").strip()
            if name and name not in testers:
                testers.append(name)
        plan_urls = [u for u in (plan.target_urls or []) if u]
        plan_reports = (
            (
                await session.execute(
                    select(Report)
                    .where(Report.testing_plan_id == plan.id)
                    .order_by(Report.create_time, Report.id)
                )
            )
            .scalars()
            .all()
        )
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
                # 当前报告优先取最近成功导出时间；无则取报告自身日期（导入报告=标题日期），
                # 保证自动导出的版本记录显示报告日期而非当前时间
                rdate = last_done.get(pr.id) or (
                    pr.create_time.strftime("%Y-%m-%d") if pr.create_time is not None else ""
                ) or export_date_str
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
                "is_retest": "复测" in (pr.title or ""),
                "creator_name": creator_name,
                "date": rdate,
            })
    meta["testers"] = testers
    meta["report_records"] = report_records

    # 漏洞章节在新报告上为临时对象，flush 后重查确保导出内容完整
    await session.flush()
    await session.refresh(report, attribute_names=["sections"])
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
                "id": v.id, "title": v.title, "vul_type": v.vul_type, "level": v.level,
                "status": v.status, "affected_url": v.affected_url, "is_retest": v.is_retest,
                "retest_html": v.retest_html,
            }
            for vid in vul_ids if (v := by_id.get(vid))
        ]
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
    await asyncio.to_thread(build_report_docx, meta, vulns, sections, docx_path, assets, plan_urls)

    # 导出版本号 +1（报告状态保持草稿，定稿仍由人工导出 Word 驱动）；
    # flush+refresh 后以最终状态写指纹，供下次导出去重判断
    report.version += 1
    await session.flush()
    await session.refresh(report)
    job = ExportJob(
        report_id=report.id,
        title=report.title,
        fmt="docx",
        status="done",
        file_path=docx_path,
        creator_id=user.id,
        report_snapshot=report.fingerprint(),
    )
    if auto_time is not None:
        job.create_time = auto_time
        job.finish_time = auto_time
    session.add(job)
