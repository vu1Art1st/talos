"""账户安全邮件令牌：邮件改绑与密码找回共用签发、校验与链接构造。"""
import hashlib
import secrets
from datetime import timedelta
from urllib.parse import quote

from fastapi import FastAPI
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.timeutil import now
from app.models import AccountActionToken, User

EMAIL_CHANGE_PURPOSE = "email_change"
PASSWORD_RESET_PURPOSE = "password_reset"
EMAIL_CHANGE_TTL_MINUTES = 60
PASSWORD_RESET_TTL_MINUTES = 30


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


async def issue_action_token(
    session: AsyncSession,
    user: User,
    purpose: str,
    *,
    new_email: str = "",
    ttl_minutes: int,
    request_ip: str = "",
) -> tuple[str, AccountActionToken]:
    """作废同用途旧令牌并签发新令牌，返回明文令牌与数据库行。"""
    await session.execute(
        update(AccountActionToken)
        .where(
            AccountActionToken.user_id == user.id,
            AccountActionToken.purpose == purpose,
            AccountActionToken.used_at.is_(None),
        )
        .values(used_at=now())
    )
    raw = secrets.token_urlsafe(32)
    row = AccountActionToken(
        user_id=user.id,
        purpose=purpose,
        token_hash=_hash_token(raw),
        new_email=new_email,
        expires_at=now() + timedelta(minutes=ttl_minutes),
        request_ip=request_ip,
    )
    session.add(row)
    await session.flush()
    return raw, row


async def consume_action_token(
    session: AsyncSession, purpose: str, raw_token: str,
) -> AccountActionToken | None:
    """校验并使用一次令牌；无效、过期、已使用统一返回 None。"""
    row = (
        await session.execute(
            select(AccountActionToken).where(
                AccountActionToken.purpose == purpose,
                AccountActionToken.token_hash == _hash_token(raw_token),
            )
        )
    ).scalar_one_or_none()
    if row is None or row.used_at is not None or row.expires_at <= now():
        return None
    row.used_at = now()
    await session.flush()
    return row


def account_link(path: str, raw_token: str) -> str:
    """令牌放 URL fragment，不进入服务端访问日志与 Referer。"""
    base = settings.PUBLIC_BASE_URL.rstrip("/")
    return f"{base}{path}#token={quote(raw_token)}"


async def send_account_email(
    app: FastAPI,
    *,
    to: str,
    subject: str,
    body_html: str,
    job_id: str,
) -> None:
    from app.workers.dispatch import dispatch

    await dispatch(
        app,
        "send_account_email_task",
        to,
        subject,
        body_html,
        job_id=job_id,
    )


def account_email_enabled() -> bool:
    return settings.account_email_enabled
