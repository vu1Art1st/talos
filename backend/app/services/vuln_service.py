"""漏洞生命周期状态机（简化版：未修复 → 修复中 → 复测中 → 已修复/已忽略/暂不处理）。"""
from app.core.timeutil import now

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import (
    PLAN_TRANSITIONS,
    STATUS_TIMESTAMP,
    VUL_STATUS,
    VUL_TRANSITIONS,
    PlanStatus,
    VulStatus,
)
from app.models import Message, User, Vul, VulLog, VulRetestRecord


def can_transition(current: int, target: int) -> bool:
    return target in VUL_TRANSITIONS.get(current, set())


def can_plan_transition(current: int, target: int) -> bool:
    """测试计划状态流转校验。"""
    return target in PLAN_TRANSITIONS.get(current, set())


async def load_vulns_or_400(session: AsyncSession, vul_ids: list[int]) -> list[Vul]:
    """按 ID 列表加载漏洞，任一不存在即 400（测试计划/春耕行动关联漏洞共用）。"""
    if not vul_ids:
        return []
    vulns = (await session.execute(select(Vul).where(Vul.id.in_(vul_ids)))).scalars().all()
    if len(vulns) != len(set(vul_ids)):
        raise HTTPException(400, "部分漏洞不存在")
    return list(vulns)


async def create_draft_vulns(
    session: AsyncSession, drafts: list, user: User, source: int,
) -> list[Vul]:
    """按草稿批量创建漏洞（春耕行动原始报告导入/快捷录入共用）。

    草稿不关联资产与测试工单，来源固定为调用方给定的专项口径；富文本
    消毒由草稿 schema 的 HtmlStr 类型完成。返回持久化后的漏洞列表。
    """
    vulns: list[Vul] = []
    for d in drafts:
        vul = Vul(
            title=d.title,
            level=d.level,
            vul_type=d.vul_type,
            source=source,
            affected_url=d.affected_url,
            description_html=d.description_html,
            reproduce_html=d.reproduce_html,
            solution_html=d.solution_html,
            submitter_id=user.id,
        )
        session.add(vul)
        vulns.append(vul)
    if vulns:
        await session.flush()
        for vul in vulns:
            add_log(session, vul, user, "创建漏洞")
    return vulns


async def _has_current_round_retest(session: AsyncSession, vul: Vul) -> bool:
    """本轮复测（最近一次进入复测中之后）是否新增了复测记录。

    - 基准时间取 vul.notice_time：漏洞处于「复测中」时该字段即最近进入复测中的打点时间，
      历史轮次的复测记录（create_time 早于该时间）不视为本轮复测结论；
    - notice_time 为空（历史数据未打点）时退化为检查是否存在任意非空复测记录，兼容旧口径。
    """
    stmt = (
        select(VulRetestRecord.id)
        .where(
            VulRetestRecord.vul_id == vul.id,
            VulRetestRecord.content_html != "",
        )
        .limit(1)
    )
    if vul.notice_time:
        stmt = stmt.where(VulRetestRecord.create_time >= vul.notice_time)
    return (await session.execute(stmt)).scalar_one_or_none() is not None


async def ensure_retest_conclusion(
    session: AsyncSession,
    vul: Vul,
    target: int,
    retest_submitted: bool = False,
) -> None:
    """复测结论校验（漏洞状态机补充规则）：

    - 变更为「已修复」：必须先经过「复测中」，且本轮复测必须已填写复测结论，
      不允许从「修复中」等状态直接跳过复测闭环；
    - 从「复测中」离开的其余结论方向——复测未通过回「修复中」、复测后回到「未修复」：
      同样强制要求填写本轮复测结论；
    - 从「已修复」重新打开为「未修复」：无特殊校验。

    复测结论判定口径（防止多轮复测时误用历史记录放行）：
    - retest_submitted=True：本次流转随请求直接提交了复测内容（报告编辑页直接填写），
      校验当前 vul.retest_html 非空即可；
    - 否则：查询是否存在「本轮复测中新增」的复测记录（create_time 不早于最近一次
      进入复测中的 notice_time），历史轮次记录不视为本轮复测结论。
    """
    if target == VulStatus.FIXED:
        if vul.status != VulStatus.RETESTING:
            raise HTTPException(
                400,
                f"不允许从「{VUL_STATUS.get(vul.status, vul.status)}」直接变更为「已修复」，"
                "必须先经过「复测中」并填写本轮复测结论",
            )
        if not await _conclusion_filled(session, vul, retest_submitted):
            raise HTTPException(400, "本轮复测尚未填写复测结论，请先新增复测记录或填写复测内容")
    elif vul.status == VulStatus.RETESTING and target in (
        VulStatus.FIXING, VulStatus.UNFIXED,
    ):
        # 复测未通过（回修复中重新整改 / 回未修复重新处理）：同样要求本轮复测结论
        if not await _conclusion_filled(session, vul, retest_submitted):
            raise HTTPException(400, "本轮复测未通过需填写复测结论，请先新增复测记录或填写复测内容")


async def _conclusion_filled(
    session: AsyncSession, vul: Vul, retest_submitted: bool,
) -> bool:
    """复测结论是否已填写：随流转直接提交的复测内容，或本轮复测新增的复测记录。"""
    if retest_submitted:
        return bool((vul.retest_html or "").strip())
    return await _has_current_round_retest(session, vul)


async def transition(
    session: AsyncSession,
    vul: Vul,
    target: int,
    operator: User,
    comment: str = "",
    retest_submitted: bool = False,
    skip_conclusion: bool = False,
) -> Vul:
    """执行状态流转：校验合法性、打时间戳、写日志、通知提交人。

    - retest_submitted：本次流转是否已随请求提交复测内容（报告编辑页直接填写 retest_html），
      用于复测结论校验时跳过「本轮复测新增记录」查询；
    - skip_conclusion：跳过复测结论校验（报告联动等系统自动流转使用，
      非人工确认复测结论，不受「本轮复测需填写结论」约束）。
    """
    if target not in VUL_STATUS:
        raise HTTPException(400, f"非法状态: {target}")
    if not can_transition(vul.status, target):
        raise HTTPException(
            400,
            f"不允许从「{VUL_STATUS.get(vul.status, vul.status)}」流转到「{VUL_STATUS[target]}」",
        )
    if not skip_conclusion:
        await ensure_retest_conclusion(session, vul, target, retest_submitted)

    old_status = vul.status
    vul.status = target
    ts_field = STATUS_TIMESTAMP.get(target)
    if ts_field:
        setattr(vul, ts_field, now())
    if target == VulStatus.RETESTING:
        vul.is_retest = True

    action = f"{VUL_STATUS[old_status]} → {VUL_STATUS[target]}"
    session.add(VulLog(
        vul_id=vul.id,
        user_id=operator.id,
        username=operator.username,
        action=action,
        content=comment,
    ))

    # 站内信通知提交人
    if vul.submitter_id and vul.submitter_id != operator.id:
        session.add(Message(
            user_id=vul.submitter_id,
            msg_type="vuln",
            title=f"漏洞「{vul.title}」状态更新",
            content=f"{operator.username} 将状态 {action}。{comment}",
        ))
    return vul


def add_log(session: AsyncSession, vul: Vul, operator: User, action: str, content: str = "") -> None:
    session.add(VulLog(
        vul_id=vul.id,
        user_id=operator.id,
        username=operator.username,
        action=action,
        content=content,
    ))


async def set_status(session: AsyncSession, vul: Vul, target: int, operator: User, comment: str = "") -> Vul:
    """直接设置状态（不受状态机流转限制，供编辑页/报告编辑页点选）：校验字典、打时间戳、写日志。"""
    if target not in VUL_STATUS:
        raise HTTPException(400, f"非法状态: {target}")
    if target == vul.status:
        return vul
    await ensure_retest_conclusion(session, vul, target)
    old_status = vul.status
    vul.status = target
    ts_field = STATUS_TIMESTAMP.get(target)
    if ts_field:
        setattr(vul, ts_field, now())
    if target == VulStatus.RETESTING:
        vul.is_retest = True
    add_log(session, vul, operator, f"{VUL_STATUS[old_status]} → {VUL_STATUS[target]}", comment)
    return vul


async def auto_transition(
    session: AsyncSession,
    vul_ids: list[int],
    target: int,
    operator: User,
    comment: str,
) -> list[Vul]:
    """批量自动流转（报告联动触发）：仅对当前状态允许流转到 target 的漏洞生效，静默跳过其余。"""
    if not vul_ids:
        return []
    vulns = (
        await session.execute(select(Vul).where(Vul.id.in_(vul_ids)))
    ).scalars().all()
    changed = []
    for vul in vulns:
        if can_transition(vul.status, target):
            # 系统自动流转（报告联动）跳过复测结论校验，避免「复测中自动回修复中」被误拦
            await transition(session, vul, target, operator, comment, skip_conclusion=True)
            changed.append(vul)
    return changed


async def sync_report_completion(session: AsyncSession, vul_ids: list[int]) -> list:
    """漏洞状态变化后双向联动测试计划（需求6：报告状态不再由漏洞闭环驱动，
    仅保留计划「复测完成/复测中」联动；报告状态由导出 Word 与内容变更管理）：
    - 某报告关联的全部漏洞均为「已修复/已忽略」时，关联计划进入「复测完成」；
    - 反向：已闭环报告出现未闭环漏洞（如已修复改回未修复）时，关联计划由「复测完成」
      回退「复测中」并重开最近一轮复测。

    返回本次新进入「复测完成」的计划对象列表（供路由层在提交后发渠道通知）。"""
    from app.models import Report, ReportSection, TestingPlan
    from app.services import plan_service

    completed: list[TestingPlan] = []
    if not vul_ids:
        return completed
    report_ids = (
        await session.execute(
            select(ReportSection.report_id)
            .where(ReportSection.vul_id.in_(vul_ids))
            .distinct()
        )
    ).scalars().all()
    for report_id in report_ids:
        linked_statuses = (
            await session.execute(
                select(Vul.status)
                .join(ReportSection, ReportSection.vul_id == Vul.id)
                .where(ReportSection.report_id == report_id)
            )
        ).scalars().all()
        if not linked_statuses:
            continue
        report = await session.get(Report, report_id)
        if report is None:
            continue
        all_closed = all(s in (VulStatus.IGNORED, VulStatus.FIXED) for s in linked_statuses)
        if report.testing_plan_id is None:
            continue
        plan = await session.get(TestingPlan, report.testing_plan_id)
        if plan is None:
            continue
        if all_closed and plan.status != PlanStatus.RETEST_DONE:
            plan.status = PlanStatus.RETEST_DONE  # 复测完成
            if not plan.retest_done_time:
                plan.retest_done_time = now().date().isoformat()
            # 当前复测轮次闭环，打完成点
            plan_service.finish_retest_round(plan)
            completed.append(plan)
        elif not all_closed and plan.status == PlanStatus.RETEST_DONE:
            plan.status = PlanStatus.RETESTING  # 复测完成 → 复测中
            plan.retest_done_time = ""
            # 撤销完成点，重开最近一轮复测
            plan_service.reopen_retest_round(plan)
    return completed
