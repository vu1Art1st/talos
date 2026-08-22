"""审计日志（F7）：登录事件与敏感操作统一写入 OperationLog。"""
import json
import logging

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutil import now
from app.models import OperationLog

logger = logging.getLogger(__name__)


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
        ip = (request.client.host if request.client else "")[:64]
        ua = (request.headers.get("user-agent", ""))[:256]
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
