"""认证依赖：JWT 会话令牌（get_current_user）与个人访问令牌（get_pat_user，F6 开放只读 API）。"""
import hashlib

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.ratelimit import get_failures, incr_failure
from app.core.security import decode_token
from app.core.timeutil import now
from app.db import get_session
from app.models import PersonalAccessToken, User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    session: AsyncSession = Depends(get_session),
) -> User:
    decoded = decode_token(token, "access")
    if decoded is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "登录已过期，请重新登录")
    user_id, ver = decoded
    user = (
        await session.execute(
            select(User).options(selectinload(User.role)).where(User.id == user_id)
        )
    ).scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "账号不存在或已禁用")
    # 令牌版本不一致（已改密/禁用）：拒绝存量令牌
    if ver != user.token_version:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "登录状态已失效，请重新登录")
    return user


def user_permissions(user: User) -> set[str]:
    if user.role is None:
        return set()
    return set(user.role.permissions or [])


async def get_pat_user(
    token: str = Depends(oauth2_scheme),
    session: AsyncSession = Depends(get_session),
) -> User:
    """开放 API 认证：仅接受 `tlp_` 前缀的个人访问令牌（只读语义，不检查角色权限）。

    - 按 sha256 查表：明文令牌不落库；
    - 校验令牌有效、未过期、所属用户启用；
    - 限流：每令牌每分钟 PAT_RATE_LIMIT 次（固定窗口），超限 429；
    - 命中后回写 last_used_at 供列表页展示最近使用时间。
    """
    if not token.startswith("tlp_"):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "开放 API 仅支持个人访问令牌（Bearer tlp_xxx）")
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    pat = (
        await session.execute(
            select(PersonalAccessToken)
            .options(selectinload(PersonalAccessToken.user))
            .where(PersonalAccessToken.token_hash == token_hash)
        )
    ).scalar_one_or_none()
    if pat is None or not pat.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "访问令牌无效或已吊销")
    if pat.expires_at is not None and pat.expires_at <= now():
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "访问令牌已过期，请重新生成")
    if pat.user is None or not pat.user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "令牌所属用户不可用")
    rl_key = f"pat_rl:{pat.id}"
    if await get_failures(rl_key, 60) >= settings.PAT_RATE_LIMIT:
        raise HTTPException(429, "请求过于频繁，请稍后再试")
    await incr_failure(rl_key, 60)
    pat.last_used_at = now()
    session.add(pat)
    await session.commit()
    return pat.user


def require_perm(perm: str):
    """权限校验依赖工厂：角色权限包含 perm 或通配符 * 时放行。"""

    async def checker(user: User = Depends(get_current_user)) -> User:
        perms = user_permissions(user)
        if "*" in perms or perm in perms:
            return user
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"缺少权限: {perm}")

    return checker


def require_pat_perm(perm: str):
    """开放 API 写操作权限校验：PAT 认证后按「令牌所属用户」的角色权限校验。

    与站内 require_perm 同口径（角色权限含 perm 或通配符 * 放行），避免个人令牌
    绕过 RBAC 执行写操作；只读端点（/open/vulns、/open/stats、工单查询）不套用此依赖。
    """

    async def checker(user: User = Depends(get_pat_user)) -> User:
        perms = user_permissions(user)
        if "*" in perms or perm in perms:
            return user
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, f"当前令牌所属账号缺少权限: {perm}",
        )

    return checker


def require_any_perm(*required: str):
    """权限校验依赖工厂：满足任一权限（或通配符 *）即放行。"""

    async def checker(user: User = Depends(get_current_user)) -> User:
        perms = user_permissions(user)
        if "*" in perms or perms & set(required):
            return user
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"缺少权限: {' / '.join(required)}")

    return checker
