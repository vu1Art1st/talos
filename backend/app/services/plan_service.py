"""测试计划辅助服务：认领权限判定、关联漏洞统计重算与复测轮次记录。"""
from app.core.timeutil import now

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import PlanStatus
from app.core.deps import user_permissions
from app.models import Report, TestingPlan, TestingPlanRetestRound, User, Vul


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
        raise HTTPException(400, "指定的测试计划不存在")
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


def is_retest_report_title(title: str) -> bool:
    """按标题判断是否为复测报告：复测报告标题约定含「复测」字样（如「XX渗透测试复测报告」）。"""
    return "复测" in (title or "")


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
    user_id: int | None = None, force: bool = False,
) -> None:
    """发起复测时记录新一轮。

    - force=False（手动流转）：已有进行中轮次则幂等跳过，防止重复计数；
    - force=True（报告实际发起复测）：上一轮未闭环即结束（视为复测未通过后再测），并开启新一轮。
    """
    unfinished = [r for r in plan.retest_rounds if r.done_time is None]
    if unfinished:
        if not force:
            return
        for r in unfinished:
            r.done_time = now()
    next_no = max((r.round_no for r in plan.retest_rounds), default=0) + 1
    session.add(TestingPlanRetestRound(
        plan_id=plan.id, round_no=next_no, source=source, creator_id=user_id,
    ))


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
