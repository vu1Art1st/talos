"""测试计划辅助服务：认领权限判定、关联漏洞统计重算与复测轮次记录。"""
from app.core.timeutil import now

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import user_permissions
from app.models import TestingPlan, TestingPlanRetestRound, User, Vul


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
