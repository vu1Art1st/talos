"""认证依赖：JWT 会话令牌（get_current_user）、个人访问令牌（get_pat_user，F6/P1-6）、
图片端点认证（get_image_viewer，安全审计 批次 E-1）。"""
import hashlib

from fastapi import Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.constants import PAT_ADMIN_READ_SCOPES, PAT_PLAN_WRITE_SCOPES, PAT_READ_SCOPES
from app.core.config import settings
from app.core.ratelimit import get_failures, incr_failure
from app.core.security import IMAGE_COOKIE, decode_token
from app.core.timeutil import now
from app.db import get_session
from app.models import PersonalAccessToken, User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

# 未改密状态（must_change_password）下仍放行的路径：登录态维护与字典下发。
# 其余接口一律 403 —— 前端虽有不可关闭的改密弹框，但没有服务端拦截时仍可直连 API 绕过。
_MUST_CHANGE_ALLOWED_PREFIXES = ("/api/v1/auth/",)
_MUST_CHANGE_ALLOWED_SUFFIXES = ("/meta",)
_MUST_CHANGE_DETAIL = "首次登录或密码已被重置，请先修改密码后再使用系统"


def _must_change_allowed(path: str) -> bool:
    return path.startswith(_MUST_CHANGE_ALLOWED_PREFIXES) or path.rstrip("/").endswith(
        _MUST_CHANGE_ALLOWED_SUFFIXES
    )


def _enforce_password_change(user: User, path: str) -> None:
    """未改密账号仅放行登录态维护与字典接口（前端强制改密的**服务端兜底**）。

    以 403 + `X-Must-Change-Password: 1` 返回：前端据此静默处理（不弹错误提示，直接弹改密框）。
    """
    if getattr(user, "must_change_password", False) and not _must_change_allowed(path):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            _MUST_CHANGE_DETAIL,
            headers={"X-Must-Change-Password": "1"},
        )


async def _load_user_by_access_token(session: AsyncSession, token: str) -> User:
    """按 access token 校验并加载用户（站内依赖与图片端点共用同一口径）。"""
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


async def get_current_user(
    request: Request,
    token: str = Depends(oauth2_scheme),
    session: AsyncSession = Depends(get_session),
) -> User:
    user = await _load_user_by_access_token(session, token)
    _enforce_password_change(user, request.url.path)
    return user


async def get_image_viewer(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> User:
    """图片端点认证（批次 E-1）：图片不再匿名可访问。

    `<img src>` 无法携带 Authorization 头，故凭证来源有两种：
    1. `Authorization: Bearer <access JWT>` 或 `Bearer <tlp_ PAT>`（API 客户端）；
    2. `vp_img` Cookie（浏览器：登录/刷新/改密时由服务端下发，HttpOnly + Path 限定到图片路径）。

    两者皆无 → 401。改密状态不拦截图片（只读资源，且改密弹框本身需要页面正常渲染）。
    """
    auth = request.headers.get("authorization", "")
    token = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
    if token.startswith("tlp_"):
        return await resolve_pat(session, token, rate_limited=False)
    if not token:
        token = request.cookies.get(IMAGE_COOKIE, "")
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "未登录或登录已过期")
    return await _load_user_by_access_token(session, token)


def user_permissions(user: User) -> set[str]:
    if user.role is None:
        return set()
    return set(user.role.permissions or [])


async def resolve_pat_row(
    session: AsyncSession,
    token: str,
    *,
    rate_limited: bool = True,
    response: Response | None = None,
) -> PersonalAccessToken:
    """按 sha256 校验个人访问令牌并返回令牌行（`resolve_pat` 与图片端点共用）。

    - 明文令牌不落库；
    - 校验令牌有效、未过期、所属用户启用；
    - `rate_limited=True`（默认）时限流每令牌每分钟 PAT_RATE_LIMIT 次（固定窗口）：
      超限返回 429 + `Retry-After`，正常请求回写 `X-RateLimit-Limit/Remaining` 头；
      图片端点按 `rate_limited=False` 调用（一张页面几十张图，逐张计数会误伤正常浏览）。
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
    if rate_limited:
        limit = max(int(settings.PAT_RATE_LIMIT), 1)
        rl_key = f"pat_rl:{pat.id}"
        used = await get_failures(rl_key, 60)
        if used >= limit:
            raise HTTPException(
                429, "请求过于频繁，请稍后再试",
                headers={
                    "Retry-After": "60",
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": "0",
                },
            )
        await incr_failure(rl_key, 60)
        if response is not None:
            response.headers.setdefault("X-RateLimit-Limit", str(limit))
            response.headers.setdefault("X-RateLimit-Remaining", str(max(limit - used - 1, 0)))
        pat.last_used_at = now()
        session.add(pat)
        await session.commit()
    return pat


async def resolve_pat(session: AsyncSession, token: str, *, rate_limited: bool = True) -> User:
    """按 sha256 校验个人访问令牌并返回所属用户（图片端点等无响应上下文场景使用）。"""
    pat = await resolve_pat_row(session, token, rate_limited=rate_limited)
    return pat.user


async def get_pat_user(
    request: Request,
    response: Response,
    token: str = Depends(oauth2_scheme),
    session: AsyncSession = Depends(get_session),
) -> User:
    """开放 API 认证：仅接受 `tlp_` 前缀的个人访问令牌。

    scope 与角色权限在各自的依赖里校验（读接口要求 scope 属于可读集合，
    写接口要求 scope 属于工单写集合且角色权限命中）；本依赖只负责认证与令牌元信息透出。
    """
    pat = await resolve_pat_row(session, token, response=response)
    # 令牌元信息透出：审计日志据此记录 PAT 名称，scope 依赖据此校验
    request.state.pat_name = pat.name
    request.state.pat_scope = pat.scope or "full"
    user = pat.user
    _enforce_password_change(user, request.url.path)
    return user


def _pat_scope(request: Request) -> str:
    return str(getattr(request.state, "pat_scope", "") or "full")


def require_pat_scope(*allowed: str):
    """要求令牌 scope 命中给定集合（缺省视为 full，兼容存量令牌）。"""

    async def checker(request: Request, _: User = Depends(get_pat_user)) -> User:
        scope = _pat_scope(request)
        if scope not in allowed:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                f"当前访问令牌 scope「{scope}」不足，需为 {' / '.join(allowed)}",
            )
        return _

    return checker


# 读接口依赖：所有 scope 均可读（显式声明，便于契约与文档一致）
require_pat_read = require_pat_scope(*PAT_READ_SCOPES)


def _has_perm(user: User, perm: str) -> bool:
    """角色权限包含 perm 或通配符 * 即放行（站内与开放 API 共用同一判定）。"""
    perms = user_permissions(user)
    return "*" in perms or perm in perms


def _has_any_perm(user: User, required: tuple[str, ...]) -> bool:
    """满足任一权限（或通配符 *）即放行。"""
    perms = user_permissions(user)
    return "*" in perms or bool(perms & set(required))


def require_perm(perm: str):
    """权限校验依赖工厂：角色权限包含 perm 或通配符 * 时放行。"""

    async def checker(user: User = Depends(get_current_user)) -> User:
        if _has_perm(user, perm):
            return user
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"缺少权限: {perm}")

    return checker


def require_pat_perm(perm: str, *, scopes: tuple[str, ...] = PAT_PLAN_WRITE_SCOPES):
    """开放 API 写操作权限校验：PAT scope 命中 **且** 令牌所属用户角色权限命中。

    - scope（P1-6）：默认要求工单写能力（`plan_write` / `full`）；只读 scope 的令牌
      即使账号有权限也不能写，避免「只读令牌被用于写操作」；
    - 角色权限：与站内 require_perm 同口径（含 perm 或通配符 * 放行），
      避免个人令牌绕过 RBAC。
    """

    async def checker(request: Request, user: User = Depends(get_pat_user)) -> User:
        scope = _pat_scope(request)
        if scope not in scopes:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                f"当前访问令牌 scope「{scope}」不足，工单写操作需为 {' / '.join(scopes)}",
            )
        if _has_perm(user, perm):
            return user
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, f"当前令牌所属账号缺少权限: {perm}",
        )

    return checker


def require_pat_admin_read(*, scopes: tuple[str, ...] = PAT_ADMIN_READ_SCOPES):
    """开放 API「管理只读」依赖（P1-6）：要求 scope 为 admin_read / full。"""
    return require_pat_scope(*scopes)


def require_any_perm(*required: str):
    """权限校验依赖工厂：满足任一权限（或通配符 *）即放行。"""

    async def checker(user: User = Depends(get_current_user)) -> User:
        if _has_any_perm(user, required):
            return user
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"缺少权限: {' / '.join(required)}")

    return checker
