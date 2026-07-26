"""漏洞生命周期状态机（沿用洞察2.0 状态语义）。"""
from datetime import datetime

from fastapi import HTTPException
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
