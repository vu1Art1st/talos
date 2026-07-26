from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.security import decode_token
from app.db import get_session
from app.models import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    session: AsyncSession = Depends(get_session),
) -> User:
    user_id = decode_token(token, "access")
    if user_id is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "登录已过期，请重新登录")
    user = (
        await session.execute(
            select(User).options(selectinload(User.role)).where(User.id == user_id)
        )
    ).scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "账号不存在或已禁用")
    return user


def user_permissions(user: User) -> set[str]:
    if user.role is None:
        return set()
    return set(user.role.permissions or [])


def require_perm(perm: str):
    """权限校验依赖工厂：角色权限包含 perm 或通配符 * 时放行。"""

    async def checker(user: User = Depends(get_current_user)) -> User:
        perms = user_permissions(user)
        if "*" in perms or perm in perms:
            return user
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"缺少权限: {perm}")

    return checker
