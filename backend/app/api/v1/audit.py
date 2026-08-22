"""审计日志查询（F7）：登录事件与敏感操作统一查询页。"""
from datetime import timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import AUDIT_ACTIONS
from app.core.deps import require_perm
from app.core.query import apply_sort, paginate
from app.core.timeutil import parse_date
from app.db import get_session
from app.models import OperationLog, User
from app.schemas import OperationLogOut, Page

router = APIRouter(prefix="/audit", tags=["审计日志"])

# 登录事件动作码（查询页「登录日志」tab 的过滤前缀）
LOGIN_ACTIONS = {a for a in AUDIT_ACTIONS if a.startswith("login_")}


@router.get("/logs", response_model=Page[OperationLogOut])
async def list_logs(
    category: str = Query("all", pattern="^(all|login|operation)$"),
    username: str = "",
    action: str = "",
    ip: str = "",
    date_from: str = "",
    date_to: str = "",
    search: str = "",
    sort: str = "",
    order: str = "desc",
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    _: User = Depends(require_perm("system:manage")),
    session: AsyncSession = Depends(get_session),
):
    cond = []
    if category == "login":
        cond.append(OperationLog.action.in_(LOGIN_ACTIONS))
    elif category == "operation":
        cond.append(OperationLog.action.notin_(LOGIN_ACTIONS))
    if username:
        cond.append(OperationLog.username.ilike(f"%{username}%"))
    if action:
        cond.append(OperationLog.action == action)
    if ip:
        cond.append(OperationLog.ip.ilike(f"%{ip}%"))
    if search:
        cond.append(OperationLog.detail.ilike(f"%{search}%"))
    d_from = parse_date(date_from)
    if d_from:
        cond.append(OperationLog.create_time >= d_from)
    d_to = parse_date(date_to)
    if d_to:
        cond.append(OperationLog.create_time < d_to + timedelta(days=1))
    stmt = apply_sort(
        select(OperationLog).where(*cond),
        OperationLog, sort, order,
        {"id", "username", "action", "create_time", "ip"},
        OperationLog.id.desc(),
    )
    total, items = await paginate(session, stmt, page, size)
    return Page(total=total, items=[OperationLogOut.model_validate(i) for i in items])
