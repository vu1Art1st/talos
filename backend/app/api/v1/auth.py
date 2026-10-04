import asyncio
import hashlib
import html
import secrets
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, Response, UploadFile, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import AVATAR_PRESETS, MESSAGE_TYPES
from app.core import token_store
from app.core.client_info import get_client_ip, get_user_agent
from app.core.config import settings
from app.core.deps import get_current_user, user_permissions
from app.core.identity import is_valid_email, normalize_email
from app.core.images import AVATAR_IMAGE_EXT, AVATAR_MAX_BYTES, normalize_avatar
from app.core.ratelimit import clear_failures, get_failures, incr_failure
from app.core.security import (
    clear_image_cookie,
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    decode_token,
    ensure_password_changed,
    hash_password,
    refresh_ttl_seconds,
    set_image_cookie,
    verify_password,
    verify_password_and_update,
)
from app.core.storage import resolve_storage_path
from app.core.timeutil import now
from app.db import get_session
from app.models import User, UserSession
from app.schemas import (
    ActionTokenIn,
    AvatarPresetIn,
    EmailChangeIn,
    MessagePrefsIn,
    PasswordIn,
    PasswordResetConfirmIn,
    PasswordResetRequestIn,
    PasswordResetStatusOut,
    ProfileIn,
    RefreshIn,
    SessionOut,
    TokenOut,
    UserOut,
)
from app.services import account_service
from app.services.audit_service import audit

router = APIRouter(prefix="/auth", tags=["认证"])

MAX_USER_SESSIONS = 5
PASSWORD_RESET_ACCOUNT_LIMIT = 3
PASSWORD_RESET_IP_LIMIT = 20
PASSWORD_RESET_WINDOW_SECONDS = 15 * 60


def _avatar_url(avatar: str) -> str:
    return f"/storage/{avatar}" if avatar.startswith("uploads/") else ""


def build_user_out(user: User) -> UserOut:
    out = UserOut.model_validate(user)
    out.role_name = user.role.name if user.role else ""
    out.permissions = sorted(user_permissions(user))
    groups = sorted((getattr(user, "groups", []) or []), key=lambda g: g.id)
    out.group_ids = [g.id for g in groups]
    out.group_names = [g.name for g in groups]
    out.avatar_url = _avatar_url(user.avatar or "")
    out.message_prefs = dict(user.message_prefs or {})
    return out


def _session_expiry():
    from datetime import timedelta

    return now() + timedelta(hours=settings.REFRESH_TOKEN_EXPIRE_HOURS)


async def _revoke_sessions(
    db: AsyncSession, user_id: int, *, except_sid: str = "",
) -> int:
    stmt = (
        update(UserSession)
        .where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
        .values(revoked_at=now())
    )
    if except_sid:
        stmt = stmt.where(UserSession.session_id != except_sid)
    result = await db.execute(stmt)
    return int(result.rowcount or 0)


async def _create_session(
    db: AsyncSession, user: User, request: Request, sid: str,
) -> None:
    active = (
        await db.execute(
            select(UserSession)
            .where(
                UserSession.user_id == user.id,
                UserSession.revoked_at.is_(None),
                UserSession.expires_at > now(),
            )
            .order_by(UserSession.create_time, UserSession.session_id)
        )
    ).scalars().all()
    excess = max(0, len(active) - MAX_USER_SESSIONS + 1)
    for old in active[:excess]:
        old.revoked_at = now()
    db.add(
        UserSession(
            session_id=sid,
            user_id=user.id,
            last_seen_at=now(),
            expires_at=_session_expiry(),
            ip=get_client_ip(request)[:64],
            user_agent=get_user_agent(request)[:256],
        )
    )
    await db.flush()


async def _refresh_session(
    db: AsyncSession, user: User, request: Request, sid: str,
) -> str:
    if not sid:
        sid = secrets.token_hex(16)
        await _create_session(db, user, request, sid)
        return sid
    row = await db.get(UserSession, sid)
    if (
        row is None
        or row.user_id != user.id
        or row.revoked_at is not None
        or row.expires_at <= now()
    ):
        raise HTTPException(401, "登录状态已失效，请重新登录")
    row.last_seen_at = now()
    row.expires_at = _session_expiry()
    row.ip = get_client_ip(request)[:64]
    row.user_agent = get_user_agent(request)[:256]
    await db.flush()
    return sid


async def _issue_tokens(
    response: Response,
    user: User,
    db: AsyncSession,
    request: Request,
    *,
    rotate_from: str | None = None,
    sid: str = "",
) -> TokenOut:
    if rotate_from is None:
        sid = secrets.token_hex(16)
        await _create_session(db, user, request, sid)
    access = create_access_token(user.id, user.token_version, sid)
    refresh, jti = create_refresh_token(user.id, user.token_version, sid)
    ttl = refresh_ttl_seconds()
    if rotate_from is None:
        await token_store.add_session(user.id, jti, ttl)
    else:
        await token_store.rotate(user.id, rotate_from, jti, ttl, settings.REFRESH_GRACE_SECONDS)
    await db.commit()
    set_image_cookie(response, access)
    return TokenOut(access_token=access, refresh_token=refresh)


@router.post("/login", response_model=TokenOut)
async def login(
    request: Request,
    response: Response,
    form: OAuth2PasswordRequestForm = Depends(),
    session: AsyncSession = Depends(get_session),
):
    client_ip = get_client_ip(request) or "?"
    fail_key = f"login_fail:{form.username}:{client_ip}"
    window = settings.LOGIN_LOCK_SECONDS
    if await get_failures(fail_key, window) >= settings.LOGIN_MAX_FAILURES:
        await audit(session, request, "login_locked", form.username, {"ip": client_ip})
        raise HTTPException(429, "登录失败次数过多，请稍后再试")
    user = (
        await session.execute(select(User).where(User.username == form.username))
    ).scalar_one_or_none()
    password_ok, updated_hash = (
        verify_password_and_update(form.password, user.password_hash)
        if user is not None
        else (False, None)
    )
    if user is None or not password_ok:
        await incr_failure(fail_key, window)
        await audit(session, request, "login_failure", form.username, {"ip": client_ip})
        raise HTTPException(401, "用户名或密码错误")
    if not user.is_active:
        await audit(session, request, "login_failure", user, {"reason": "账号已禁用"})
        raise HTTPException(403, "账号已禁用")
    await clear_failures(fail_key)
    user.last_login = now()
    if updated_hash:
        user.password_hash = updated_hash
    await session.commit()
    await audit(session, request, "login_success", user, {"ip": client_ip})
    return await _issue_tokens(response, user, session, request)


@router.post("/refresh", response_model=TokenOut)
async def refresh(
    body: RefreshIn,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
):
    decoded = decode_refresh_token(body.refresh_token)
    if decoded is None:
        raise HTTPException(401, "refresh token 无效")
    user_id, ver, jti, sid = decoded
    user = await session.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(401, "账号不存在或已禁用")
    if ver != user.token_version:
        raise HTTPException(401, "登录状态已失效，请重新登录")
    if not await token_store.is_acceptable(user_id, jti):
        raise HTTPException(401, "登录状态已失效，请重新登录")
    sid = await _refresh_session(session, user, request, sid)
    return await _issue_tokens(response, user, session, request, rotate_from=jti, sid=sid)


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
):
    try:
        payload = await request.json()
    except Exception:  # noqa: BLE001
        payload = {}
    raw_refresh = str((payload or {}).get("refresh_token") or "")
    jti = ""
    uid: int | None = None
    sid = ""
    decoded = decode_refresh_token(raw_refresh) if raw_refresh else None
    if decoded is not None:
        uid, _ver, jti, sid = decoded
    else:
        auth = request.headers.get("authorization", "")
        header_token = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
        access = decode_token(header_token, "access") if header_token else None
        if access is not None:
            uid, _ver, sid = access
    if uid is not None:
        await token_store.end_session(uid, jti)
        if sid:
            row = await session.get(UserSession, sid)
            if row is not None and row.user_id == uid:
                row.revoked_at = now()
                await session.commit()
        await audit(session, request, "logout", await session.get(User, uid))
    clear_image_cookie(response)
    return {"msg": "已退出登录"}


@router.get("/me", response_model=UserOut)
async def me(
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
):
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        set_image_cookie(response, auth[7:].strip())
    return build_user_out(user)


@router.put("/profile", response_model=UserOut)
async def update_profile(
    body: ProfileIn,
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    user.realname = body.realname
    user.phone = body.phone
    await session.commit()
    await audit(session, request, "profile_update", user)
    return build_user_out(user)


async def _remove_avatar_file(avatar: str) -> None:
    if not avatar.startswith("uploads/"):
        return
    try:
        path = resolve_storage_path(avatar)
        await asyncio.to_thread(Path(path).unlink, missing_ok=True)
    except Exception:  # noqa: BLE001
        return


async def _save_avatar(
    request: Request,
    user: User,
    session: AsyncSession,
    avatar: str,
) -> UserOut:
    old = user.avatar
    user.avatar = avatar
    await session.commit()
    if old and old != avatar:
        await _remove_avatar_file(old)
    await audit(session, request, "avatar_change", user)
    return build_user_out(user)


@router.post("/avatar", response_model=UserOut)
async def upload_avatar(
    request: Request,
    file: UploadFile,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    ext = Path(file.filename or "").suffix.lower()
    if ext not in AVATAR_IMAGE_EXT:
        raise HTTPException(400, "头像仅支持 PNG、JPEG、WebP")
    data = await file.read()
    if len(data) > AVATAR_MAX_BYTES:
        raise HTTPException(400, "头像大小不能超过 2MB")
    try:
        processed = await asyncio.to_thread(normalize_avatar, data)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    name = f"{uuid.uuid4().hex}.webp"
    (settings.storage_sub("uploads", "images") / name).write_bytes(processed)
    return await _save_avatar(request, user, session, f"uploads/images/{name}")


@router.put("/avatar", response_model=UserOut)
async def set_avatar_preset(
    body: AvatarPresetIn,
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    if body.preset_id not in AVATAR_PRESETS:
        raise HTTPException(400, "预置头像不存在")
    return await _save_avatar(request, user, session, f"preset:{body.preset_id}")


@router.delete("/avatar", response_model=UserOut)
async def reset_avatar(
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    return await _save_avatar(request, user, session, "")


@router.get("/preferences", response_model=MessagePrefsIn)
async def get_preferences(user: User = Depends(get_current_user)):
    return MessagePrefsIn(disabled_types=list((user.message_prefs or {}).get("disabled_types") or []))


@router.put("/preferences", response_model=MessagePrefsIn)
async def update_preferences(
    body: MessagePrefsIn,
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    disabled = sorted(set(body.disabled_types))
    unknown = [item for item in disabled if item not in MESSAGE_TYPES]
    if unknown:
        raise HTTPException(400, f"未知的消息类型: {', '.join(unknown)}")
    if "system" in disabled:
        raise HTTPException(400, "系统消息不能关闭")
    user.message_prefs = {"disabled_types": disabled}
    await session.commit()
    await audit(session, request, "message_prefs_update", user, {"disabled_types": disabled})
    return MessagePrefsIn(disabled_types=disabled)


@router.get("/sessions", response_model=list[SessionOut])
async def list_sessions(
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    rows = (
        await session.execute(
            select(UserSession)
            .where(
                UserSession.user_id == user.id,
                UserSession.revoked_at.is_(None),
                UserSession.expires_at > now(),
            )
            .order_by(UserSession.create_time.desc())
        )
    ).scalars().all()
    current_sid = str(getattr(request.state, "session_id", "") or "")
    return [
        SessionOut(
            id=row.session_id,
            create_time=row.create_time,
            last_seen_at=row.last_seen_at,
            expires_at=row.expires_at,
            ip=row.ip,
            user_agent=row.user_agent,
            is_current=row.session_id == current_sid,
        )
        for row in rows
    ]


@router.delete("/sessions/{session_id}")
async def revoke_session(
    session_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    row = await session.get(UserSession, session_id)
    if row is None or row.user_id != user.id or row.revoked_at is not None:
        raise HTTPException(404, "会话不存在")
    row.revoked_at = now()
    await session.commit()
    await audit(session, request, "session_revoke", user, {"session_id": session_id})
    return {"msg": "已退出该设备", "current": session_id == getattr(request.state, "session_id", "")}


@router.post("/sessions/revoke-others")
async def revoke_other_sessions(
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    current_sid = str(getattr(request.state, "session_id", "") or "")
    count = await _revoke_sessions(session, user.id, except_sid=current_sid)
    await session.commit()
    await audit(session, request, "session_revoke", user, {"scope": "others", "count": count})
    return {"msg": "已退出其他设备", "count": count}


async def _send_account_link_email(
    request: Request,
    user: User,
    raw_token: str,
    *,
    token_id: int,
    purpose: str,
    to_email: str,
) -> None:
    path = "/profile/email-confirm" if purpose == account_service.EMAIL_CHANGE_PURPOSE else "/reset-password"
    link = account_service.account_link(path, raw_token)
    subject = "[Talos] 确认更换邮箱" if purpose == account_service.EMAIL_CHANGE_PURPOSE else "[Talos] 重置密码"
    action = "确认邮箱变更" if purpose == account_service.EMAIL_CHANGE_PURPOSE else "重置账号密码"
    body = (
        f"<p>您好，{html.escape(user.realname or user.username)}：</p>"
        f"<p>请在有效期内点击以下链接{action}：</p>"
        f'<p><a href="{html.escape(link, quote=True)}">{html.escape(link)}</a></p>'
        "<p>如非本人操作，请忽略本邮件。</p>"
    )
    await account_service.send_account_email(
        request.app,
        to=to_email,
        subject=subject,
        body_html=body,
        job_id=f"account-email:{purpose}:{token_id}",
    )


@router.post("/email-change", status_code=status.HTTP_202_ACCEPTED)
async def request_email_change(
    body: EmailChangeIn,
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    if not account_service.account_email_enabled():
        raise HTTPException(400, "邮件服务未启用，请联系管理员")
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(400, "当前密码错误")
    if body.new_email == normalize_email(user.email):
        raise HTTPException(400, "新邮箱不能与当前邮箱相同")
    exists = (
        await session.execute(
            select(User.id).where(
                func.lower(User.email) == body.new_email,
                User.id != user.id,
            )
        )
    ).scalar_one_or_none()
    if exists is not None:
        raise HTTPException(400, "该邮箱已被使用")
    raw, row = await account_service.issue_action_token(
        session,
        user,
        account_service.EMAIL_CHANGE_PURPOSE,
        new_email=body.new_email,
        ttl_minutes=account_service.EMAIL_CHANGE_TTL_MINUTES,
        request_ip=get_client_ip(request),
    )
    await session.commit()
    await audit(
        session,
        request,
        "email_change_request",
        user,
        {"new_email_domain": body.new_email.rsplit("@", 1)[-1]},
    )
    await _send_account_link_email(
        request,
        user,
        raw,
        token_id=row.id,
        purpose=account_service.EMAIL_CHANGE_PURPOSE,
        to_email=body.new_email,
    )
    return {"msg": "确认邮件已发送，请查收新邮箱"}


@router.post("/email-change/confirm")
async def confirm_email_change(
    body: ActionTokenIn,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    row = await account_service.consume_action_token(
        session, account_service.EMAIL_CHANGE_PURPOSE, body.token,
    )
    if row is None or not is_valid_email(row.new_email):
        raise HTTPException(400, "链接无效或已过期")
    user = await session.get(User, row.user_id)
    if user is None:
        raise HTTPException(400, "链接无效或已过期")
    exists = (
        await session.execute(
            select(User.id).where(
                func.lower(User.email) == row.new_email,
                User.id != user.id,
            )
        )
    ).scalar_one_or_none()
    if exists is not None:
        raise HTTPException(400, "该邮箱已被使用")
    user.email = row.new_email
    await session.commit()
    await audit(
        session,
        request,
        "email_change_complete",
        user,
        {"new_email_domain": row.new_email.rsplit("@", 1)[-1]},
    )
    return {"msg": "邮箱更换成功"}


@router.get("/password-reset/status", response_model=PasswordResetStatusOut)
async def password_reset_status():
    return PasswordResetStatusOut(enabled=account_service.account_email_enabled())


@router.post("/password-reset/request", status_code=status.HTTP_202_ACCEPTED)
async def request_password_reset(
    body: PasswordResetRequestIn,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    client_ip = get_client_ip(request) or "?"
    ip_key = f"pwd_reset_ip:{client_ip}"
    if await get_failures(ip_key, PASSWORD_RESET_WINDOW_SECONDS) >= PASSWORD_RESET_IP_LIMIT:
        raise HTTPException(429, "请求过于频繁，请稍后再试")
    await incr_failure(ip_key, PASSWORD_RESET_WINDOW_SECONDS)
    generic = {"msg": "如该邮箱对应有效账号，重置邮件将发送，请稍后查收"}
    if not account_service.account_email_enabled() or not is_valid_email(body.email):
        return generic
    email_hash = hashlib.sha256(body.email.encode("utf-8")).hexdigest()[:24]
    account_key = f"pwd_reset_account:{email_hash}"
    if await get_failures(account_key, PASSWORD_RESET_WINDOW_SECONDS) >= PASSWORD_RESET_ACCOUNT_LIMIT:
        return generic
    await incr_failure(account_key, PASSWORD_RESET_WINDOW_SECONDS)
    user = (
        await session.execute(
            select(User).where(func.lower(User.email) == body.email, User.is_active.is_(True))
        )
    ).scalar_one_or_none()
    if user is None:
        await audit(
            session, request, "password_reset_request", None,
            {"email_domain": body.email.rsplit("@", 1)[-1], "sent": False},
        )
        return generic
    raw, row = await account_service.issue_action_token(
        session,
        user,
        account_service.PASSWORD_RESET_PURPOSE,
        ttl_minutes=account_service.PASSWORD_RESET_TTL_MINUTES,
        request_ip=client_ip,
    )
    await session.commit()
    await audit(
        session, request, "password_reset_request", user,
        {"sent": True, "email_domain": body.email.rsplit("@", 1)[-1]},
    )
    await _send_account_link_email(
        request,
        user,
        raw,
        token_id=row.id,
        purpose=account_service.PASSWORD_RESET_PURPOSE,
        to_email=body.email,
    )
    return generic


@router.post("/password-reset/confirm")
async def confirm_password_reset(
    body: PasswordResetConfirmIn,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    row = await account_service.consume_action_token(
        session, account_service.PASSWORD_RESET_PURPOSE, body.token,
    )
    if row is None:
        raise HTTPException(400, "链接无效或已过期")
    user = await session.get(User, row.user_id)
    if user is None or not user.is_active:
        raise HTTPException(400, "链接无效或已过期")
    try:
        ensure_password_changed(body.new_password, user.password_hash)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    user.password_hash = hash_password(body.new_password)
    user.must_change_password = False
    user.token_version += 1
    await _revoke_sessions(session, user.id)
    await session.commit()
    await token_store.end_all(user.id)
    await audit(session, request, "password_reset_complete", user)
    return {"msg": "密码已重置，请使用新密码登录"}


@router.post("/password", status_code=status.HTTP_200_OK)
async def change_password(
    body: PasswordIn,
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    if not verify_password(body.old_password, user.password_hash):
        raise HTTPException(400, "原密码错误")
    try:
        ensure_password_changed(body.new_password, user.password_hash)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    user.password_hash = hash_password(body.new_password)
    user.must_change_password = False
    user.token_version += 1
    await _revoke_sessions(session, user.id)
    await session.commit()
    await token_store.end_all(user.id)
    await audit(session, request, "password_change", user)
    return {"msg": "密码修改成功，请重新登录"}
