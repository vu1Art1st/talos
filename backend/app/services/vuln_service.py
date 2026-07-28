"""漏洞生命周期状态机（简化版：未修复 → 修复中 → 复测中 → 已修复/已忽略/暂不处理）。"""
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import STATUS_TIMESTAMP, VUL_STATUS, VUL_TRANSITIONS
from app.models import Message, User, Vul, VulLog


def can_transition(current: int, target: int) -> bool:
    return target in VUL_TRANSITIONS.get(current, set())


async def transition(
    session: AsyncSession,
    vul: Vul,
    target: int,
    operator: User,
    comment: str = "",
) -> Vul:
    """执行状态流转：校验合法性、打时间戳、写日志、通知提交人。"""
    if target not in VUL_STATUS:
        raise HTTPException(400, f"非法状态: {target}")
    if not can_transition(vul.status, target):
        raise HTTPException(
            400,
            f"不允许从「{VUL_STATUS.get(vul.status, vul.status)}」流转到「{VUL_STATUS[target]}」",
        )

    old_status = vul.status
    vul.status = target
    ts_field = STATUS_TIMESTAMP.get(target)
    if ts_field:
        setattr(vul, ts_field, datetime.utcnow())
    if target == 55:
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
            await transition(session, vul, target, operator, comment)
            changed.append(vul)
    return changed


async def sync_report_completion(session: AsyncSession, vul_ids: list[int]) -> None:
    """漏洞状态变化后联动报告：某报告关联的全部漏洞均为「已修复/已忽略」时，报告自动标记 completed。
    报告关联测试计划时，计划同步进入「复测完成」。"""
    from datetime import date

    from app.models import Report, ReportSection, TestingPlan

    if not vul_ids:
        return
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
        if linked_statuses and all(s in (20, 60) for s in linked_statuses):
            report = await session.get(Report, report_id)
            if report and report.status != "completed":
                report.status = "completed"
                if report.testing_plan_id is not None:
                    plan = await session.get(TestingPlan, report.testing_plan_id)
                    if plan is not None:
                        plan.status = 60  # 复测完成
                        if not plan.retest_done_time:
                            plan.retest_done_time = date.today().isoformat()
