from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.deps import get_current_user, user_permissions
from app.core.ratelimit import clear_failures, get_failures, incr_failure
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.core.timeutil import utcnow
from app.db import get_session
from app.models import User
from app.schemas import PasswordIn, RefreshIn, TokenOut, UserOut

router = APIRouter(prefix="/auth", tags=["认证"])


def build_user_out(user: User) -> UserOut:
    out = UserOut.model_validate(user)
    out.role_name = user.role.name if user.role else ""
    out.permissions = sorted(user_permissions(user))
    return out


@router.post("/login", response_model=TokenOut)
async def login(
    request: Request,
    form: OAuth2PasswordRequestForm = Depends(),
    session: AsyncSession = Depends(get_session),
):
    # 防爆破：同一用户名+客户端 IP 失败达阈则锁定一段时间
    client_ip = request.client.host if request.client else "?"
    fail_key = f"login_fail:{form.username}:{client_ip}"
    window = settings.LOGIN_LOCK_SECONDS
    if await get_failures(fail_key, window) >= settings.LOGIN_MAX_FAILURES:
        raise HTTPException(429, "登录失败次数过多，请稍后再试")
    user = (
        await session.execute(select(User).where(User.username == form.username))
    ).scalar_one_or_none()
    if user is None or not verify_password(form.password, user.password_hash):
        await incr_failure(fail_key, window)
        raise HTTPException(401, "用户名或密码错误")
    if not user.is_active:
        raise HTTPException(403, "账号已禁用")
    await clear_failures(fail_key)
    user.last_login = utcnow()
    await session.commit()
    return TokenOut(
        access_token=create_access_token(user.id, user.token_version),
        refresh_token=create_refresh_token(user.id, user.token_version),
    )


@router.post("/refresh", response_model=TokenOut)
async def refresh(body: RefreshIn, session: AsyncSession = Depends(get_session)):
    decoded = decode_token(body.refresh_token, "refresh")
    if decoded is None:
        raise HTTPException(401, "refresh token 无效")
    user_id, ver = decoded
    user = await session.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(401, "账号不存在或已禁用")
    if ver != user.token_version:
        raise HTTPException(401, "登录状态已失效，请重新登录")
    return TokenOut(
        access_token=create_access_token(user.id, user.token_version),
        refresh_token=create_refresh_token(user.id, user.token_version),
    )


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)):
    return build_user_out(user)


@router.post("/password", response_model=TokenOut)
async def change_password(
    body: PasswordIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    if not verify_password(body.old_password, user.password_hash):
        raise HTTPException(400, "原密码错误")
    user.password_hash = hash_password(body.new_password)
    user.must_change_password = False
    # 递增令牌版本使旧令牌失效，并为当前会话下发新令牌
    user.token_version += 1
    session.add(user)
    await session.commit()
    return TokenOut(
        access_token=create_access_token(user.id, user.token_version),
        refresh_token=create_refresh_token(user.id, user.token_version),
    )
