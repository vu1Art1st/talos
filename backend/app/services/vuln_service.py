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


def set_status(session: AsyncSession, vul: Vul, target: int, operator: User, comment: str = "") -> Vul:
    """直接设置状态（不受状态机流转限制，供编辑页/报告编辑页点选）：校验字典、打时间戳、写日志。"""
    if target not in VUL_STATUS:
        raise HTTPException(400, f"非法状态: {target}")
    if target == vul.status:
        return vul
    old_status = vul.status
    vul.status = target
    ts_field = STATUS_TIMESTAMP.get(target)
    if ts_field:
        setattr(vul, ts_field, datetime.utcnow())
    if target == 55:
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
            await transition(session, vul, target, operator, comment)
            changed.append(vul)
    return changed


async def sync_report_completion(session: AsyncSession, vul_ids: list[int]) -> None:
    """漏洞状态变化后双向联动报告与测试计划：
    - 某报告关联的全部漏洞均为「已修复/已忽略」时，报告自动标记 completed，关联计划进入「复测完成」；
    - 反向：已 completed 的报告出现未闭环漏洞（如已修复改回未修复）时，报告回退 draft，
      关联计划由「复测完成」回退「复测中」并重开最近一轮复测。"""
    from datetime import date

    from app.models import Report, ReportSection, TestingPlan
    from app.services import plan_service

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
        if not linked_statuses:
            continue
        report = await session.get(Report, report_id)
        if report is None:
            continue
        all_closed = all(s in (20, 60) for s in linked_statuses)
        if all_closed and report.status != "completed":
            report.status = "completed"
            if report.testing_plan_id is not None:
                plan = await session.get(TestingPlan, report.testing_plan_id)
                if plan is not None:
                    plan.status = 60  # 复测完成
                    if not plan.retest_done_time:
                        plan.retest_done_time = date.today().isoformat()
                    # 当前复测轮次闭环，打完成点
                    plan_service.finish_retest_round(plan)
        elif not all_closed and report.status == "completed":
            report.status = "draft"
            if report.testing_plan_id is not None:
                plan = await session.get(TestingPlan, report.testing_plan_id)
                if plan is not None and plan.status == 60:
                    plan.status = 50  # 复测完成 → 复测中
                    plan.retest_done_time = ""
                    # 撤销完成点，重开最近一轮复测
                    plan_service.reopen_retest_round(plan)
