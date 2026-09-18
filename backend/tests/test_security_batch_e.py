"""批次 E 安全加固测试：图片鉴权下发、refresh 轮换、未改密拦截、解压配额。

对应项：
- E-1 / TALOS-2026-006：`/storage/uploads/images/<name>` 需登录（Cookie 或 Bearer），匿名 401；
- E-3：refresh token 一次性轮换（宽限期内允许并发，宽限外/退出/改密后失效）；
- E-5：docx/xlsx 解压配额（zip 炸弹）；
- E-6：`must_change_password` 服务端强制（未改密仅放行 /auth/* 与 /meta）。
"""
import io
import zipfile

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.core import token_store
from app.core.archive import assert_archive_quota
from app.core.config import settings
from app.core.security import IMAGE_COOKIE, create_refresh_token
from app.db import async_session_maker
from app.models import User

ADMIN = {"username": "admin", "password": "admin123"}


async def _login(client, username: str = "admin", password: str = "admin123") -> dict:
    resp = await client.post("/api/v1/auth/login", data={"username": username, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _anonymous_client() -> AsyncClient:
    """无任何凭证的独立客户端。

    会话级 `client` 夹具在登录时接收了 vp_img Cookie（httpx 自动保存），
    直接用它无法表达「匿名请求」，故另起一个不带 Cookie 的客户端。
    """
    from app.main import app

    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


# ---------- E-1：图片需登录 ----------
async def test_image_anonymous_denied_and_authenticated_allowed(client, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "STORAGE_DIR", str(tmp_path))
    name = "a" * 32 + ".png"
    img = tmp_path / "uploads" / "images" / name
    img.parent.mkdir(parents=True)
    img.write_bytes(b"\x89PNG\r\n\x1a\nfake-image")
    url = f"/storage/uploads/images/{name}"
    access = (await _login(client))["access_token"]

    async with await _anonymous_client() as anon:
        # 匿名（既无 Cookie 也无 Authorization）→ 401，不再静态直出
        assert (await anon.get(url)).status_code == 401
        # API 客户端形态：Bearer 头
        assert (await anon.get(
            url, headers={"Authorization": f"Bearer {access}"},
        )).status_code == 200
        # 浏览器形态：vp_img Cookie（<img> 无法携带 Authorization 头）
        anon.cookies.set(IMAGE_COOKIE, access)
        assert (await anon.get(url)).status_code == 200
        # 非法令牌
        anon.cookies.set(IMAGE_COOKIE, "not-a-token")
        assert (await anon.get(url)).status_code == 401
        # 越界/非法文件名与不存在的文件一律 404
        anon.cookies.set(IMAGE_COOKIE, access)
        assert (await anon.get("/storage/uploads/images/%2e%2e%2fpasswd")).status_code == 404
        assert (await anon.get(f"/storage/uploads/images/{'b' * 32}.png")).status_code == 404


async def test_login_sets_scoped_image_cookie(client):
    resp = await client.post("/api/v1/auth/login", data=ADMIN)
    assert resp.status_code == 200
    cookie = resp.headers.get("set-cookie", "")
    assert IMAGE_COOKIE in cookie
    assert "HttpOnly" in cookie
    assert "Path=/storage/uploads/images" in cookie  # 作用域限定，不随其它请求发送
    assert "SameSite=lax" in cookie.replace("samesite", "SameSite")


async def test_logout_clears_image_cookie(client):
    tokens = await _login(client)
    resp = await client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": tokens["refresh_token"]},
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert resp.status_code == 200, resp.text
    assert "Path=/storage/uploads/images" in resp.headers.get("set-cookie", "")


# ---------- E-3：refresh 轮换 ----------
async def test_refresh_rotates_and_rejects_old_token_after_grace(client, monkeypatch):
    first = await _login(client)
    # 宽限期置 0：轮换后旧 jti 立即失效（等价于「宽限窗口已过」）
    monkeypatch.setattr(settings, "REFRESH_GRACE_SECONDS", 0)
    resp = await client.post("/api/v1/auth/refresh", json={"refresh_token": first["refresh_token"]})
    assert resp.status_code == 200, resp.text
    rotated = resp.json()
    assert rotated["refresh_token"] != first["refresh_token"]  # 每次刷新都换新令牌

    # 旧令牌（已轮换且超出宽限）不得再兑换
    resp = await client.post("/api/v1/auth/refresh", json={"refresh_token": first["refresh_token"]})
    assert resp.status_code == 401, resp.text
    # 新令牌可用
    assert (await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": rotated["refresh_token"]},
    )).status_code == 200


async def test_refresh_allows_old_token_within_grace(client):
    """宽限期内允许旧令牌再兑换一次：多标签页/并发刷新的正常形态。"""
    first = await _login(client)
    assert (await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": first["refresh_token"]},
    )).status_code == 200
    assert (await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": first["refresh_token"]},
    )).status_code == 200


async def test_refresh_rejects_unknown_jti(client):
    """自行签发、未登记的 jti（伪造/已清理会话）→ 401。"""
    token, _jti = create_refresh_token(1, 0)
    resp = await client.post("/api/v1/auth/refresh", json={"refresh_token": token})
    assert resp.status_code == 401, resp.text


async def test_multi_device_sessions_are_independent(client):
    a = await _login(client)
    b = await _login(client)
    assert (await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": a["refresh_token"]},
    )).status_code == 200
    # 设备 A 轮换不影响设备 B
    assert (await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": b["refresh_token"]},
    )).status_code == 200


async def test_logout_invalidates_refresh_token(client):
    tokens = await _login(client)
    await client.post(
        "/api/v1/auth/logout", json={"refresh_token": tokens["refresh_token"]},
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert (await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]},
    )).status_code == 401


async def test_password_change_invalidates_other_sessions(client, auth):
    """改密＝凭证轮换：其它设备的 refresh token 一并失效（token_version + 轮换状态清空）。

    使用专用账号：改密会递增 token_version，若直接改 admin 口令会让会话级 `auth` 夹具的
    令牌失效，连带影响后续所有用例。
    """
    role_id = (await client.post(
        "/api/v1/roles", headers=auth,
        json={"name": "改密轮换角色", "permissions": ["vuln:submit"], "remark": ""},
    )).json()["id"]
    await client.post(
        "/api/v1/users", headers=auth,
        json={"username": "pwd_rotate", "password": "Init@12345", "realname": "改密用例",
              "email": "", "phone": "", "is_active": True, "role_id": role_id},
    )

    other = await _login(client, "pwd_rotate", "Init@12345")
    current = await _login(client, "pwd_rotate", "Init@12345")
    resp = await client.post(
        "/api/v1/auth/password",
        headers={"Authorization": f"Bearer {current['access_token']}"},
        json={"old_password": "Init@12345", "new_password": "Rotated@12345"},
    )
    assert resp.status_code == 200, resp.text
    # 另一设备的 refresh token 随之失效
    assert (await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": other["refresh_token"]},
    )).status_code == 401


# ---------- E-5：压缩包配额 ----------
def _bomb_zip(total_mb: int = 60) -> bytes:
    """高压缩比 zip：全零内容压缩后极小，解压后极大。"""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("bomb.bin", b"\x00" * (total_mb * 1024 * 1024))
    return buf.getvalue()


def test_archive_quota_rejects_zip_bomb():
    with pytest.raises(Exception) as exc:
        assert_archive_quota(_bomb_zip(), max_entries=500, max_uncompressed_mb=50, max_ratio=50)
    assert getattr(exc.value, "status_code", None) == 400


def test_archive_quota_rejects_too_many_entries():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for i in range(30):
            zf.writestr(f"f{i}.txt", b"x")
    with pytest.raises(Exception) as exc:
        assert_archive_quota(buf.getvalue(), max_entries=10)
    assert getattr(exc.value, "status_code", None) == 400


def test_archive_quota_passes_normal_document():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", b"<Types/>")
        zf.writestr("word/document.xml", b"<w:document/>" * 100)
    assert_archive_quota(buf.getvalue()) is None  # 正常文档不受影响


def test_archive_quota_ignores_non_zip():
    assert_archive_quota(b"not a zip at all") is None  # 交由调用方的解析错误处理


# ---------- E-6：未改密服务端拦截 ----------
async def test_must_change_password_blocks_business_endpoints(client, auth):
    role_id = (await client.post(
        "/api/v1/roles", headers=auth,
        json={"name": "未改密角色", "permissions": ["vuln:submit"], "remark": ""},
    )).json()["id"]
    resp = await client.post(
        "/api/v1/users", headers=auth,
        json={"username": "must_pwd_user", "password": "Init@12345", "realname": "首登用户",
              "email": "", "phone": "", "is_active": True, "role_id": role_id},
    )
    assert resp.status_code == 200, resp.text

    tokens = await _login(client, "must_pwd_user", "Init@12345")
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    # 业务接口被拦：403 + X-Must-Change-Password 标记（前端据此静默处理）
    resp = await client.get("/api/v1/vulns", headers=headers)
    assert resp.status_code == 403, resp.text
    assert resp.headers.get("x-must-change-password") == "1"
    # 字典接口与登录态接口放行，保证改密弹框能正常渲染
    assert (await client.get("/api/v1/auth/me", headers=headers)).status_code == 200
    assert (await client.get("/api/v1/meta", headers=headers)).status_code == 200

    # 改密后立即恢复可用
    resp = await client.post(
        "/api/v1/auth/password", headers=headers,
        json={"old_password": "Init@12345", "new_password": "Changed@12345"},
    )
    assert resp.status_code == 200, resp.text
    new_headers = {"Authorization": f"Bearer {resp.json()['access_token']}"}
    assert (await client.get("/api/v1/vulns", headers=new_headers)).status_code == 200


async def test_must_change_password_blocks_pat(client, auth):
    """未改密账号的 PAT 同样被拦（令牌不能绕过首登改密）。"""
    role_id = (await client.post(
        "/api/v1/roles", headers=auth,
        json={"name": "未改密PAT角色", "permissions": ["vuln:submit"], "remark": ""},
    )).json()["id"]
    await client.post(
        "/api/v1/users", headers=auth,
        json={"username": "must_pwd_pat", "password": "Init@12345", "realname": "首登PAT",
              "email": "", "phone": "", "is_active": True, "role_id": role_id},
    )
    headers = await _login_and_change(client, "must_pwd_pat", "Init@12345")
    resp = await client.post("/api/v1/pats", headers=headers, json={"name": "t", "expire_days": 7})
    assert resp.status_code == 200, resp.text
    pat = {"Authorization": f"Bearer {resp.json()['token']}"}

    # 直接把内部标记置位（管理接口不暴露该字段），模拟「管理员重置口令后尚未改密」
    async with async_session_maker() as session:
        user = (
            await session.execute(select(User).where(User.username == "must_pwd_pat"))
        ).scalar_one()
        user.must_change_password = True
        await session.commit()

    resp = await client.get("/api/v1/open/vulns", headers=pat)
    assert resp.status_code == 403, resp.text
    assert resp.headers.get("x-must-change-password") == "1"


async def _login_and_change(client, username: str, password: str) -> dict:
    tokens = await _login(client, username, password)
    resp = await client.post(
        "/api/v1/auth/password",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
        json={"old_password": password, "new_password": f"{password}x"},
    )
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


async def test_refresh_session_state_cleared_on_login_limit():
    """轮换状态写入/清理的最小自检（Redis 不可用时走进程内降级）。"""
    await token_store.end_all(999999)  # 幂等：不存在的用户不报错
    await token_store.add_session(999999, "jti-1", 60)
    assert await token_store.is_acceptable(999999, "jti-1") is True
    assert await token_store.is_acceptable(999999, "jti-x") is False
    # 兼容升级前无 jti 的老令牌
    assert await token_store.is_acceptable(999999, "") is True
    await token_store.end_all(999999)
    assert await token_store.is_acceptable(999999, "jti-1") is False
