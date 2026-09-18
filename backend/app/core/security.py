"""口令哈希与 JWT 令牌签发/校验，以及图片访问 Cookie 的下发/清除。

令牌类型：
- access（默认 120 分钟）：Authorization: Bearer 携带；图片端点还可用 Cookie 携带（见下）。
- refresh（默认 24 小时）：仅 `/auth/refresh` 使用，**带 jti** 以支持一次性轮换
  （安全审计 批次 E-3，状态存于 core/token_store.py）。
"""
import uuid
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Response
from passlib.context import CryptContext

from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

ALGORITHM = "HS256"

# 图片访问凭证：<img src> 无法携带 Authorization 头，只能由浏览器自动带 Cookie。
# 作用域限定到图片路径（Path=/storage/uploads/images），不会随其它请求发送；
# HttpOnly（JS 读不到）+ SameSite=Lax（跨站子资源不带）；Secure 由部署环境决定（HTTPS 才开）。
IMAGE_COOKIE = "vp_img"
IMAGE_COOKIE_PATH = "/storage/uploads/images"


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return pwd_context.verify(plain, hashed)
    except ValueError:
        return False


def _create_token(
    sub: str, token_type: str, expires_delta: timedelta, ver: int, jti: str = "",
) -> str:
    now = datetime.now(timezone.utc)
    payload = {"sub": sub, "type": token_type, "ver": ver, "iat": now, "exp": now + expires_delta}
    if jti:
        payload["jti"] = jti
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=ALGORITHM)


def create_access_token(user_id: int, ver: int = 0) -> str:
    return _create_token(str(user_id), "access", timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES), ver)


def create_refresh_token(user_id: int, ver: int = 0) -> tuple[str, str]:
    """签发 refresh token，返回 `(token, jti)`。

    jti 用于轮换状态存储（core/token_store.py）：每次刷新旧 jti 立即失效（宽限期内除外），
    避免同一 refresh token 在有效期内被无限次重复兑换。
    """
    jti = uuid.uuid4().hex
    token = _create_token(
        str(user_id), "refresh", timedelta(hours=settings.REFRESH_TOKEN_EXPIRE_HOURS), ver, jti,
    )
    return token, jti


def decode_token(token: str, expected_type: str = "access") -> tuple[int, int] | None:
    """校验并返回 (用户 id, 令牌版本号)，失败返回 None。"""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        return None
    if payload.get("type") != expected_type:
        return None
    try:
        return int(payload["sub"]), int(payload.get("ver", 0))
    except (KeyError, ValueError):
        return None


def decode_refresh_token(token: str) -> tuple[int, int, str] | None:
    """校验 refresh token，返回 (用户 id, 令牌版本号, jti)；jti 缺失（升级前签发的老令牌）返回空串。"""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        return None
    if payload.get("type") != "refresh":
        return None
    try:
        return int(payload["sub"]), int(payload.get("ver", 0)), str(payload.get("jti") or "")
    except (KeyError, ValueError):
        return None


def refresh_ttl_seconds() -> int:
    """refresh 轮换状态的 TTL：与 token 自身有效期一致。"""
    return settings.REFRESH_TOKEN_EXPIRE_HOURS * 3600


def set_image_cookie(response: Response, access_token: str) -> None:
    """下发图片访问 Cookie（每次签发新 access token 时同步刷新，避免与令牌生命周期脱节）。"""
    response.set_cookie(
        key=IMAGE_COOKIE,
        value=access_token,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        path=IMAGE_COOKIE_PATH,
        httponly=True,
        samesite="lax",
        secure=settings.COOKIE_SECURE,
    )


def clear_image_cookie(response: Response) -> None:
    """清除图片访问 Cookie（退出登录；HttpOnly 无法由 JS 删除，必须服务端下发清除）。"""
    response.delete_cookie(IMAGE_COOKIE, path=IMAGE_COOKIE_PATH)
