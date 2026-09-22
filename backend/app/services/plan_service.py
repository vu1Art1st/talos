"""测试计划辅助服务：认领权限判定、关联漏洞统计重算与复测轮次记录。"""
from app.core.timeutil import now

from fastapi import HTTPException
from sqlalchemy import and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.constants import PlanStatus, VulStatus
from app.core.deps import user_permissions
from app.models import (
    Report,
    ReportSection,
    TestingPlan,
    TestingPlanRetestRound,
    User,
    Vul,
)


def can_operate(user: User, plan: TestingPlan) -> bool:
    """认领者或管理员（权限含 *）才可修改测试状态、生成报告等计划级操作。"""
    if "*" in user_permissions(user):
        return True
    return any(u.id == user.id for u in plan.testers)


def is_plan_claimant(user: User, plan: TestingPlan) -> bool:
    """严格认领判定：仅已认领该计划的账号具备录入/编辑漏洞的权限。

    与 can_operate 的区别：不因角色权限含 *（管理员）而放行。需求为
    「录入漏洞阶段仅认领该计划的账号可修改和录入漏洞，其他账号无权限」，
    即使管理员未认领该计划也不能录入/编辑其漏洞（可先认领后再操作）。"""
    return any(u.id == user.id for u in plan.testers)


async def get_plan_or_400(session: AsyncSession, plan_id: int) -> TestingPlan:
    plan = await session.get(TestingPlan, plan_id)
    if plan is None:
        raise HTTPException(400, "指定的渗透测试工单不存在")
    return plan


async def reopen_passed_plan(session: AsyncSession, plan_id: int | None) -> bool:
    """已确认「测试通过（无漏洞）」的计划再次关联到漏洞时，自动重开为「初测中」。

    无漏洞闭环与漏洞重开双向联动：新漏洞录入/关联后不再停留在已闭环终态，
    由测试人员重新走初测流程。无漏洞测试结论保留以便追溯。返回是否发生重开。
    """
    if plan_id is None:
        return False
    plan = await session.get(TestingPlan, plan_id)
    if plan is None or plan.status != PlanStatus.PASSED:
        return False
    plan.status = PlanStatus.TESTING
    return True


async def refresh_stats(session: AsyncSession, plan_id: int | None) -> None:
    """按关联漏洞 level（10超/20高/30中/40低）重算四项统计；无关联漏洞时保留手填值。"""
    if plan_id is None:
        return
    plan = await session.get(TestingPlan, plan_id)
    if plan is None:
        return
    rows = (
        await session.execute(
            select(Vul.level, func.count(Vul.id))
            .where(Vul.testing_plan_id == plan_id)
            .group_by(Vul.level)
        )
    ).all()
    if not rows:
        return
    counts = dict(rows)
    plan.stat_critical = counts.get(10, 0)
    plan.stat_high = counts.get(20, 0)
    plan.stat_medium = counts.get(30, 0)
    plan.stat_low = counts.get(40, 0)


# 复测报告标题标记：Python 判定与 SQL 条件（结论的「周期内生成复测报告」）共用同一来源
RETEST_TITLE_MARK = "复测"


def is_retest_report_title(title: str) -> bool:
    """按标题判断是否为复测报告：复测报告标题约定含「复测」字样（如「XX渗透测试复测报告」）。"""
    return RETEST_TITLE_MARK in (title or "")


def retest_state_of(*, is_retest: bool, triggered: bool, all_closed: bool) -> str:
    """报告维度的复测状态：`none` 未发起复测 / `ongoing` 复测中 / `done` 复测完成。

    - is_retest：报告自身即复测报告（标题含「复测」）；
    - triggered：本报告已发起过复测，口径见 `retest_triggered_report_ids`（权威关联 ∪ 覆盖代偿）；
    - all_closed：该报告章节内漏洞是否全部闭环（已修复/已忽略）。

    两者皆不成立 → 未发起复测；已发起但仍有未闭环漏洞 → 复测中；章节漏洞全部闭环 → 复测完成。
    与工单级「复测完成」口径不同：工单还包含未纳入本报告章节的漏洞，二者可能不同步（符合预期）。
    """
    if not (is_retest or triggered):
        return "none"
    return "done" if all_closed else "ongoing"


async def report_closure_map(
    session: AsyncSession, report_ids: list[int],
) -> dict[int, tuple[int, int]]:
    """报告 → (关联漏洞总数, 已完成数)：已完成口径与工单复测状态一致（已修复/已忽略）。

    一次分组查询供工单流程抽屉标注「本报告漏洞已全部完成」，避免逐报告查询。
    未关联任何漏洞的报告不会出现在结果中（调用方按 (0, 0) 兜底）。
    """
    ids = [rid for rid in dict.fromkeys(report_ids) if rid is not None]
    if not ids:
        return {}
    rows = (
        await session.execute(
            select(
                ReportSection.report_id,
                func.count(Vul.id),
                func.sum(
                    case((Vul.status.in_((VulStatus.IGNORED, VulStatus.FIXED)), 1), else_=0)
                ),
            )
            .join(Vul, Vul.id == ReportSection.vul_id)
            .where(ReportSection.report_id.in_(ids))
            .group_by(ReportSection.report_id)
        )
    ).all()
    return {rid: (int(total or 0), int(closed or 0)) for rid, total, closed in rows}


async def retest_triggered_report_ids(
    session: AsyncSession, report_ids: list[int],
) -> set[int]:
    """入参报告 id 中「已发起过复测」的集合（`retest_state_of` 的 `triggered` 判据）。

    工单流程抽屉与报告管理列表共用本函数，禁止各接口另行推演。两个来源合并：

    1. **权威关联**：轮次 `src_report_id` 指向该报告（2.19.0 起由「发起复测」入口写入）；
    2. **覆盖代偿**：`src_report_id` 为空且本轮有复测报告的轮次（「报告导入复测」与 2.19.0
       前的存量轮次），按「本轮复测报告章节漏洞 ∩ 该报告章节漏洞 ≠ ∅」归因。

    代偿只作用于**无权威关联**的轮次：复测报告章节由源报告章节派生，交集存在即说明本报告的
    漏洞已被该轮复测覆盖；而「有权威关联」的轮次仍只认 `src_report_id`，避免把复测发起之后
    新建、恰好复用同一漏洞的报告误标为已发起复测。
    """
    ids = [rid for rid in dict.fromkeys(report_ids) if rid is not None]
    if not ids:
        return set()
    triggered = set(
        (
            await session.execute(
                select(TestingPlanRetestRound.src_report_id).where(
                    TestingPlanRetestRound.src_report_id.in_(ids)
                )
            )
        ).scalars().all()
    )
    src_section = aliased(ReportSection)
    cov_section = aliased(ReportSection)
    covered_report = aliased(Report)
    covered = (
        await session.execute(
            select(cov_section.report_id)
            .select_from(TestingPlanRetestRound)
            .join(src_section, src_section.report_id == TestingPlanRetestRound.report_id)
            .join(cov_section, cov_section.vul_id == src_section.vul_id)
            .join(
                covered_report,
                and_(
                    covered_report.id == cov_section.report_id,
                    covered_report.testing_plan_id == TestingPlanRetestRound.plan_id,
                ),
            )
            .where(
                TestingPlanRetestRound.src_report_id.is_(None),
                TestingPlanRetestRound.report_id.is_not(None),
                cov_section.report_id.in_(ids),
            )
            .distinct()
        )
    ).scalars().all()
    triggered.update(covered)
    return triggered


async def infer_src_report_id(
    session: AsyncSession, plan_id: int, report_id: int,
) -> int | None:
    """按「章节漏洞交集最大且唯一」在同工单内推断复测报告的源报告（初测报告）。

    供「报告导入复测」入库时补写轮次 `src_report_id` 与存量轮次回填脚本复用（同一规则）：
    复测报告章节由源报告章节派生，交集最大者即源报告。候选仅取同工单、标题不含
    `RETEST_TITLE_MARK` 的报告；无交集或并列最大时返回 None（不做猜测）。
    """
    retest_vul_ids = set(
        (
            await session.execute(
                select(ReportSection.vul_id).where(
                    ReportSection.report_id == report_id,
                    ReportSection.vul_id.is_not(None),
                )
            )
        ).scalars().all()
    )
    if not retest_vul_ids:
        return None
    rows = (
        await session.execute(
            select(ReportSection.report_id)
            .join(Report, Report.id == ReportSection.report_id)
            .where(
                Report.testing_plan_id == plan_id,
                Report.id != report_id,
                Report.title.not_ilike(f"%{RETEST_TITLE_MARK}%"),
                ReportSection.vul_id.in_(retest_vul_ids),
            )
        )
    ).scalars().all()
    overlap: dict[int, int] = {}
    for rid in rows:
        overlap[rid] = overlap.get(rid, 0) + 1
    if not overlap:
        return None
    best = max(overlap.values())
    winners = [rid for rid, count in overlap.items() if count == best]
    return winners[0] if len(winners) == 1 else None


async def fill_report_closure(session: AsyncSession, plans: list) -> None:
    """为工单响应对象（TestingPlanOut）填充各报告「漏洞闭环进度」与「复测状态」派生字段。

    `all_closed` 仅在报告存在关联漏洞且全部完成时为 True（无漏洞/空报告不视为已完成）；
    `retest_state` 口径见 `retest_state_of`（是否已发起复测取自 `retest_triggered_report_ids`）。
    """
    report_ids = [r.id for p in plans for r in (p.reports or [])]
    closure = await report_closure_map(session, report_ids)
    triggered = await retest_triggered_report_ids(session, report_ids)
    for p in plans:
        for r in (p.reports or []):
            total, closed = closure.get(r.id, (0, 0))
            r.vul_total = total
            r.vul_closed = closed
            r.all_closed = total > 0 and closed == total
            r.is_retest = is_retest_report_title(r.title)
            r.retest_state = retest_state_of(
                is_retest=r.is_retest, triggered=r.id in triggered, all_closed=r.all_closed,
            )


async def report_retest_state_map(
    session: AsyncSession, reports: list[tuple[int, str]],
) -> dict[int, str]:
    """报告管理页批量取复测状态：入参 `[(report_id, title)]`，返回 `{report_id: none|ongoing|done}`。

    一次取章节漏洞闭环与「已发起复测的报告」（口径见 `retest_triggered_report_ids`），避免逐报告查询。
    """
    ids = [rid for rid, _ in reports if rid is not None]
    if not ids:
        return {}
    closure = await report_closure_map(session, ids)
    triggered = await retest_triggered_report_ids(session, ids)
    states: dict[int, str] = {}
    for rid, title in reports:
        total, closed = closure.get(rid, (0, 0))
        states[rid] = retest_state_of(
            is_retest=is_retest_report_title(title),
            triggered=rid in triggered,
            all_closed=total > 0 and closed == total,
        )
    return states


async def refresh_mandays(session: AsyncSession, plan_id: int | None) -> None:
    """测试计划实际人天自动计算：仅纳入初测报告（标题不含「复测」）的人天之和。

    与漏洞统计口径一致：有关联初测报告时自动重算并覆盖手填值；
    无初测报告（含仅有关联复测报告）时保留手填值，复测报告人天不计入统计。
    已手动修正（actual_mandays_override=True）时跳过自动覆盖，保留修正值；
    取消修正后（标志置 False）再调用本函数即恢复为初测报告计算的人天。
    """
    if plan_id is None:
        return
    plan = await session.get(TestingPlan, plan_id)
    if plan is None:
        return
    if plan.actual_mandays_override:
        return
    # 同一会话中 plan 可能已存在（复用实例不触发 selectin 预加载），显式刷新 reports 避免 MissingGreenlet
    await session.refresh(plan, attribute_names=["reports"])
    first_test_reports = [
        r for r in plan.reports if not is_retest_report_title(r.title)
    ]
    if not first_test_reports:
        return
    plan.actual_mandays = round(
        float(sum(r.actual_mandays or 0 for r in first_test_reports)), 2
    )


def start_retest_round(
    session: AsyncSession, plan: TestingPlan, source: str,
    user_id: int | None = None, force: bool = False, report_id: int | None = None,
    src_report_id: int | None = None,
) -> TestingPlanRetestRound | None:
    """发起复测时记录新一轮，返回新轮次（幂等跳过时返回 None）。

    - force=False（手动流转）：已有进行中轮次则幂等跳过，防止重复计数；
    - force=True（报告实际发起复测）：上一轮未闭环即结束（视为复测未通过后再测），并开启新一轮；
    - report_id：本轮次关联的复测报告，删除该报告时据此回退轮次，保持复测轮数与报告一致；
    - src_report_id：发起本轮的**源报告**（初测报告），供报告维度判定「是否已发起复测」；
      手动流转与报告导入复测无源报告，保持为空。
    """
    unfinished = [r for r in plan.retest_rounds if r.done_time is None]
    if unfinished:
        if not force:
            return None
        for r in unfinished:
            r.done_time = now()
    next_no = max((r.round_no for r in plan.retest_rounds), default=0) + 1
    round_row = TestingPlanRetestRound(
        plan_id=plan.id, round_no=next_no, source=source,
        creator_id=user_id, report_id=report_id, src_report_id=src_report_id,
    )
    session.add(round_row)
    return round_row


async def rollback_retest_round_by_report(
    session: AsyncSession, plan: TestingPlan, report_id: int,
) -> None:
    """删除由某份复测报告发起的复测轮次（删除复测报告时回退复测轮数）。

    - 移除 report_id 匹配的轮次记录（即该次发起复测新增的轮次），复测轮数相应减少；
    - 该轮次若为 force 发起，其上一轮已被强制打完成点；删除后若计划仍处于「复测中」
      且无任何进行中轮次，则撤销最近一轮的完成点（与 start_retest_round(force=True) 对称），
      保证轮次状态与计划状态一致。
    """
    removed = [r for r in plan.retest_rounds if r.report_id == report_id]
    if not removed:
        return
    for r in removed:
        await session.delete(r)
    await session.flush()
    remaining = [r for r in plan.retest_rounds if r.report_id != report_id]
    if plan.status == PlanStatus.RETESTING and not any(r.done_time is None for r in remaining):
        finished = [r for r in remaining if r.done_time is not None]
        if finished:
            finished[-1].done_time = None


def finish_retest_round(plan: TestingPlan) -> None:
    """复测完成时为当前进行中的轮次打完成点。"""
    for r in plan.retest_rounds:
        if r.done_time is None:
            r.done_time = now()


def reopen_retest_round(plan: TestingPlan) -> None:
    """漏洞回退导致计划重新进入复测中时，撤销最近一轮的完成点（与 finish_retest_round 对称）。"""
    finished = [r for r in plan.retest_rounds if r.done_time is not None]
    if finished:
        finished[-1].done_time = None
