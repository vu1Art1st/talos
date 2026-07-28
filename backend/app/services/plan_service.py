"""测试计划辅助服务：认领权限判定与关联漏洞统计重算。"""
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import user_permissions
from app.models import TestingPlan, User, Vul


def can_operate(user: User, plan: TestingPlan) -> bool:
    """认领者或管理员（权限含 *）才可修改测试状态、录入漏洞。"""
    if "*" in user_permissions(user):
        return True
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
