"""审计日志（F7）：登录事件与敏感操作统一写入 OperationLog。"""
import json
import logging

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.client_info import get_client_ip, get_user_agent
from app.core.timeutil import now
from app.models import OperationLog, User

logger = logging.getLogger(__name__)


async def resolve_realnames(
    session: AsyncSession, items: list,
) -> tuple[dict[int, str], dict[str, str]]:
    """为日志记录（OperationLog / VulLog）批量解析用户姓名（realname）。

    返回 ({user_id: realname}, {username: realname}) 两个映射，调用方按
    user_id 命中优先、username 兜底（覆盖登录失败等 user_id 为空的记录）；
    未设置姓名的返回空串，展示层回退用户名。
    """
    user_ids = {i.user_id for i in items if getattr(i, "user_id", None)}
    usernames = {i.username for i in items if getattr(i, "username", "")}
    by_id: dict[int, str] = {}
    by_name: dict[str, str] = {}
    if user_ids:
        for u in (await session.execute(select(User).where(User.id.in_(user_ids)))).scalars():
            by_id[u.id] = u.realname or ""
    if usernames:
        for u in (await session.execute(select(User).where(User.username.in_(usernames)))).scalars():
            by_name[u.username] = u.realname or ""
    return by_id, by_name


async def audit(
    session: AsyncSession,
    request: Request | None,
    action: str,
    user=None,
    detail: dict | None = None,
) -> None:
    """写一条审计日志。独立提交，失败仅告警不影响主流程。

    - request 为 None 时（无请求上下文的调用）IP/UA 留空
    - user 传 ORM User 或 None（登录失败时可能查不到用户），username 支持直接传字符串
    """
    ip = ""
    ua = ""
    if request is not None:
        ip = get_client_ip(request)[:64]
        ua = get_user_agent(request)[:256]
    username = user if isinstance(user, str) else getattr(user, "username", "") or ""
    user_id = getattr(user, "id", None) if not isinstance(user, str) else None
    try:
        session.add(OperationLog(
            user_id=user_id,
            username=username,
            action=action,
            detail=json.dumps(detail, ensure_ascii=False) if detail else "",
            ip=ip,
            user_agent=ua,
            create_time=now(),
        ))
        await session.commit()
    except Exception as exc:  # noqa: BLE001  审计失败不阻断业务
        logger.warning("写审计日志失败 action=%s: %s", action, exc)
        await session.rollback()
