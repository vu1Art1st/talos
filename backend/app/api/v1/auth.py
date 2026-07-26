from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, user_permissions
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
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
    form: OAuth2PasswordRequestForm = Depends(),
    session: AsyncSession = Depends(get_session),
):
    user = (
        await session.execute(select(User).where(User.username == form.username))
    ).scalar_one_or_none()
    if user is None or not verify_password(form.password, user.password_hash):
        raise HTTPException(401, "用户名或密码错误")
    if not user.is_active:
        raise HTTPException(403, "账号已禁用")
    user.last_login = datetime.utcnow()
    await session.commit()
    return TokenOut(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
    )


@router.post("/refresh", response_model=TokenOut)
async def refresh(body: RefreshIn, session: AsyncSession = Depends(get_session)):
    user_id = decode_token(body.refresh_token, "refresh")
    if user_id is None:
        raise HTTPException(401, "refresh token 无效")
    user = await session.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(401, "账号不存在或已禁用")
    return TokenOut(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
    )


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)):
    return build_user_out(user)


@router.post("/password")
async def change_password(
    body: PasswordIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    if not verify_password(body.old_password, user.password_hash):
        raise HTTPException(400, "原密码错误")
    user.password_hash = hash_password(body.new_password)
    user.must_change_password = False
    session.add(user)
    await session.commit()
    return {"msg": "修改成功"}
