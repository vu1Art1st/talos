"""Word 导入确认入库：解析校验、报告批次编排、知识库回填、去重合并与收尾。

路由层（api/v1/imports.py::confirm_batch）只做参数编排与消息汇总，
本模块按「解析校验 → 报告编排 → 知识库回填 → 去重合并/建漏洞 → 收尾」承接全部业务逻辑。
事务统一由路由层 commit，本模块只做 flush（保证自增 ID 可用）。
"""
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutil import now
from app.models import (
    Asset,
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
    # 复测轮次为惰性关系，新建计划需显式加载后才能在同步逻辑中访问
    await session.refresh(plan, attribute_names=["retest_rounds"])
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


async def resolve_report_asset(
    session: AsyncSession, batch: ImportBatch, plan: TestingPlan, asset: Asset | None,
) -> Asset | None:
    """报告格式批次的资产编排：按系统名匹配/自动创建（补被测 URL/IP），
    无系统名但计划已关联资产时默认入库到首个关联资产；最后把资产关联到计划。"""
    batch_meta = batch.meta_json or {}
    system_name = (batch_meta.get("system_name") or "").strip()
    if asset is None:
        if system_name:
            asset = (
                await session.execute(select(Asset).where(Asset.name == system_name))
            ).scalars().first()
            target_url = (batch_meta.get("target_url") or "").strip()
            target_ip = (batch_meta.get("target_ip") or "").strip()
            if asset is None:
                remark = "导入报告自动创建"
                if target_ip:
                    remark += f"；被测IP：{target_ip}"
                asset = Asset(name=system_name, remark=remark)
                session.add(asset)
            if target_url:
                urls = list(asset.internal_urls or [])
                if target_url not in urls:
                    urls.append(target_url)
                    asset.internal_urls = urls
            await session.flush()
        elif plan.asset_ids:
            # 无系统名但计划已关联资产时，默认入库到首个关联资产
            asset = await session.get(Asset, plan.asset_ids[0])
    # 本次入库的资产自动关联到计划，保持「资产关联前置至计划」的一致性
    if asset is not None:
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
        report = Report(
            title=batch.filename.rsplit(".", 1)[0],
            project_name=(batch_meta.get("system_name") or "").strip() or plan.system_name,
            target_ip=(batch_meta.get("target_ip") or ""),
            testing_plan_id=plan.id,
            creator_id=user.id,
            status="draft",  # 需求6：新生成报告一律为草稿，定稿由导出 Word 驱动
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
