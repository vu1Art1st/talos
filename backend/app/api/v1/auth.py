from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import token_store
from app.core.client_info import get_client_ip
from app.core.config import settings
from app.core.deps import get_current_user, user_permissions
from app.core.ratelimit import clear_failures, get_failures, incr_failure
from app.core.security import (
    clear_image_cookie,
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    decode_token,
    hash_password,
    refresh_ttl_seconds,
    set_image_cookie,
    verify_password,
)
from app.core.timeutil import now
from app.db import get_session
from app.models import User
from app.schemas import PasswordIn, RefreshIn, TokenOut, UserOut
from app.services.audit_service import audit

router = APIRouter(prefix="/auth", tags=["认证"])


def build_user_out(user: User) -> UserOut:
    out = UserOut.model_validate(user)
    out.role_name = user.role.name if user.role else ""
    out.permissions = sorted(user_permissions(user))
    return out


async def _issue_tokens(
    response: Response, user: User, *, rotate_from: str | None = None,
) -> TokenOut:
    """签发 access + refresh，登记轮换状态，并刷新图片 Cookie（三个签发点共用）。

    - `rotate_from=None`（登录/改密）：登记新会话（改密场景前需先 end_all，见 change_password）；
    - `rotate_from=<旧 jti>`（刷新）：轮换，旧 jti 进入宽限期。
    """
    access = create_access_token(user.id, user.token_version)
    refresh, jti = create_refresh_token(user.id, user.token_version)
    ttl = refresh_ttl_seconds()
    if rotate_from is None:
        await token_store.add_session(user.id, jti, ttl)
    else:
        await token_store.rotate(user.id, rotate_from, jti, ttl, settings.REFRESH_GRACE_SECONDS)
    set_image_cookie(response, access)
    return TokenOut(access_token=access, refresh_token=refresh)


@router.post("/login", response_model=TokenOut)
async def login(
    request: Request,
    response: Response,
    form: OAuth2PasswordRequestForm = Depends(),
    session: AsyncSession = Depends(get_session),
):
    # 防爆破：同一用户名+客户端 IP 失败达阈则锁定一段时间
    client_ip = get_client_ip(request) or "?"
    fail_key = f"login_fail:{form.username}:{client_ip}"
    window = settings.LOGIN_LOCK_SECONDS
    if await get_failures(fail_key, window) >= settings.LOGIN_MAX_FAILURES:
        await audit(session, request, "login_locked", form.username, {"ip": client_ip})
        raise HTTPException(429, "登录失败次数过多，请稍后再试")
    user = (
        await session.execute(select(User).where(User.username == form.username))
    ).scalar_one_or_none()
    if user is None or not verify_password(form.password, user.password_hash):
        await incr_failure(fail_key, window)
        await audit(session, request, "login_failure", form.username, {"ip": client_ip})
        raise HTTPException(401, "用户名或密码错误")
    if not user.is_active:
        await audit(session, request, "login_failure", user, {"reason": "账号已禁用"})
        raise HTTPException(403, "账号已禁用")
    await clear_failures(fail_key)
    user.last_login = now()
    await session.commit()
    await audit(session, request, "login_success", user, {"ip": client_ip})
    return await _issue_tokens(response, user)


@router.post("/refresh", response_model=TokenOut)
async def refresh(
    body: RefreshIn,
    response: Response,
    session: AsyncSession = Depends(get_session),
):
    decoded = decode_refresh_token(body.refresh_token)
    if decoded is None:
        raise HTTPException(401, "refresh token 无效")
    user_id, ver, jti = decoded
    user = await session.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(401, "账号不存在或已禁用")
    if ver != user.token_version:
        raise HTTPException(401, "登录状态已失效，请重新登录")
    # 轮换校验（批次 E-3）：只接受活跃 jti 或宽限期内刚被轮换掉的 jti；
    # 被重复使用的旧令牌（含已被清空的会话）一律 401，需重新登录。
    if not await token_store.is_acceptable(user_id, jti):
        raise HTTPException(401, "登录状态已失效，请重新登录")
    return await _issue_tokens(response, user, rotate_from=jti)


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
):
    """退出登录：注销当前会话的 refresh token 并清除图片 Cookie（幂等）。

    不强制要求请求头带有效令牌（令牌可能刚好过期），按请求体 refresh token 反查会话、
    其次按 Authorization 头反查用户；`vp_img` 是 HttpOnly，前端 JS 无法删除，只能由本接口清除。
    """
    try:
        payload = await request.json()
    except Exception:  # noqa: BLE001  无请求体/非法 JSON 时按空处理
        payload = {}
    raw_refresh = str((payload or {}).get("refresh_token") or "")
    jti = ""
    uid: int | None = None
    decoded = decode_refresh_token(raw_refresh) if raw_refresh else None
    if decoded is not None:
        uid, _ver, jti = decoded
    else:
        auth = request.headers.get("authorization", "")
        header_token = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
        access = decode_token(header_token, "access") if header_token else None
        uid = access[0] if access else None
    if uid is not None:
        await token_store.end_session(uid, jti)
        # 带上用户对象以便审计行记录 username（与其它动作口径一致）
        await audit(session, request, "logout", await session.get(User, uid))
    clear_image_cookie(response)
    return {"msg": "已退出登录"}


@router.get("/me", response_model=UserOut)
async def me(
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
):
    """当前用户信息；顺带续订图片 Cookie。

    前端每次启动都会调用本接口，因此升级前已登录的用户无需重新登录即可恢复图片显示
    （图片鉴权依赖 vp_img Cookie，见 core/security.set_image_cookie）。
    """
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        set_image_cookie(response, auth[7:].strip())
    return build_user_out(user)


@router.post("/password", response_model=TokenOut)
async def change_password(
    body: PasswordIn,
    request: Request,
    response: Response,
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
    # 改密＝凭证轮换：清空该用户全部轮换状态（其它设备的 refresh token 一并失效）
    await token_store.end_all(user.id)
    await audit(session, request, "password_change", user)
    return await _issue_tokens(response, user)
