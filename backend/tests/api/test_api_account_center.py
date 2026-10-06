"""API 集成测试：密码策略、个人中心、会话、邮箱改绑与邮件找回。"""
import re
from io import BytesIO
from urllib.parse import unquote
from uuid import uuid4

import pytest
from httpx import AsyncClient
from PIL import Image
from sqlalchemy import select

from _helpers import _login_ready
from app.core.config import settings
from app.core.security import create_access_token, decode_token
from app.db import async_session_maker
from app.models import Message, User
from app.services import account_service, message_service

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _create_ready_user(
    client: AsyncClient, auth: dict, *, prefix: str, email: str = "",
) -> tuple[int, str, dict]:
    username = f"{prefix}_{uuid4().hex[:8]}"
    resp = await client.post(
        "/api/v1/users",
        headers=auth,
        json={
            "username": username,
            "password": "Init@12345",
            "realname": "个人中心用例",
            "email": email,
            "phone": "",
            "is_active": True,
            "role_id": None,
        },
    )
    assert resp.status_code == 200, resp.text
    user_id = resp.json()["id"]
    headers = await _login_ready(client, username, "Init@12345")
    return user_id, f"{username}", headers


def _capture_account_email(monkeypatch) -> list[dict]:
    captured: list[dict] = []

    async def fake_send(app, *, to: str, subject: str, body_html: str, job_id: str) -> None:
        captured.append({"to": to, "subject": subject, "html": body_html, "job_id": job_id})

    monkeypatch.setattr(account_service, "send_account_email", fake_send)
    monkeypatch.setattr(settings, "SMTP_HOST", "smtp.test")
    monkeypatch.setattr(settings, "PUBLIC_BASE_URL", "https://talos.example.com")
    return captured


def _extract_token(message: dict) -> str:
    match = re.search(r"#token=([^\"<]+)", message["html"])
    assert match is not None
    return unquote(match.group(1))


async def test_password_duplicate_rejected_for_self_admin_and_reset(
    client: AsyncClient, auth: dict, monkeypatch,
):
    user_id, username, user_auth = await _create_ready_user(
        client, auth, prefix="password_rule", email=f"{uuid4().hex[:8]}@example.com",
    )
    current = "Init@12345x"
    resp = await client.post(
        "/api/v1/auth/password",
        headers=user_auth,
        json={"old_password": current, "new_password": current},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "新密码不能与原密码相同"

    resp = await client.put(
        f"/api/v1/users/{user_id}",
        headers=auth,
        json={
            "username": username,
            "password": current,
            "realname": "个人中心用例",
            "email": "",
            "phone": "",
            "is_active": True,
            "role_id": None,
            "group_ids": [],
        },
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "新密码不能与原密码相同"

    async with async_session_maker() as session:
        user = await session.get(User, user_id)
        user.email = f"{uuid4().hex[:8]}@example.com"
        await session.commit()

    captured = _capture_account_email(monkeypatch)
    resp = await client.post("/api/v1/auth/password-reset/request", json={"email": user.email})
    assert resp.status_code == 202
    token = _extract_token(captured[-1])
    resp = await client.post(
        "/api/v1/auth/password-reset/confirm",
        json={"token": token, "new_password": current},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "新密码不能与原密码相同"

    new_password = "Reset@12345"
    resp = await client.post(
        "/api/v1/auth/password-reset/confirm",
        json={"token": token, "new_password": new_password},
    )
    assert resp.status_code == 200, resp.text
    assert (
        await client.post(
            "/api/v1/auth/login", data={"username": username, "password": new_password},
        )
    ).status_code == 200


async def test_profile_avatar_preferences_and_message_filter(client: AsyncClient, auth: dict):
    user_id, _username, user_auth = await _create_ready_user(
        client, auth, prefix="profile",
    )
    resp = await client.put(
        "/api/v1/auth/profile",
        headers=user_auth,
        json={"realname": "资料已更新", "phone": "13800000000"},
    )
    assert resp.status_code == 200
    assert resp.json()["realname"] == "资料已更新"
    assert resp.json()["phone"] == "13800000000"

    image = Image.new("RGB", (400, 220), "#059669")
    output = BytesIO()
    image.save(output, format="PNG")
    resp = await client.post(
        "/api/v1/auth/avatar",
        headers=user_auth,
        files={"file": ("avatar.png", output.getvalue(), "image/png")},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["avatar_url"].startswith("/storage/uploads/images/")

    resp = await client.put(
        "/api/v1/auth/avatar", headers=user_auth, json={"preset_id": "zzz/1.3/01"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["avatar"] == "preset:zzz/1.3/01"
    preset_url = resp.json()["avatar_url"]
    assert preset_url == "/storage/avatars/zzz/1.3/01.webp"

    image_resp = await client.get(preset_url, headers=user_auth)
    assert image_resp.status_code == 200, image_resp.text
    assert image_resp.headers["content-type"] == "image/webp"
    assert image_resp.content[:4] == b"RIFF" and image_resp.content[8:12] == b"WEBP"

    # 未在白名单内的 id 不参与任何路径拼接，设置与读取都拒绝
    assert (
        await client.put("/api/v1/auth/avatar", headers=user_auth, json={"preset_id": "zzz/1.3/99"})
    ).status_code == 400
    assert (await client.get("/storage/avatars/zzz/1.3/99.webp", headers=user_auth)).status_code == 404
    assert (await client.delete("/api/v1/auth/avatar", headers=user_auth)).json()["avatar"] == ""

    resp = await client.put(
        "/api/v1/auth/preferences", headers=user_auth, json={"disabled_types": ["sla"]},
    )
    assert resp.status_code == 200
    assert resp.json()["disabled_types"] == ["sla"]
    assert (
        await client.put(
            "/api/v1/auth/preferences", headers=user_auth, json={"disabled_types": ["system"]},
        )
    ).status_code == 400

    async with async_session_maker() as session:
        assert await message_service.create_message(
            session, user_id, "sla", "不应写入",
        ) is None
        assert await message_service.create_message(
            session, user_id, "system", "系统消息",
        ) is not None
        await session.commit()
        rows = (
            await session.execute(select(Message).where(Message.user_id == user_id))
        ).scalars().all()
    assert [row.msg_type for row in rows] == ["system"]


async def test_session_revoke_is_immediate(client: AsyncClient, auth: dict):
    _user_id, username, ready_headers = await _create_ready_user(client, auth, prefix="session")
    second = (
        await client.post(
            "/api/v1/auth/login", data={"username": username, "password": "Init@12345x"},
        )
    ).json()
    second_headers = {"Authorization": f"Bearer {second['access_token']}"}
    sessions = (await client.get("/api/v1/auth/sessions", headers=second_headers)).json()
    assert len(sessions) == 2
    other = next(row for row in sessions if not row["is_current"])
    assert (await client.delete(f"/api/v1/auth/sessions/{other['id']}", headers=second_headers)).status_code == 200
    assert (await client.get("/api/v1/auth/me", headers=second_headers)).status_code == 200
    assert (await client.get("/api/v1/auth/me", headers=ready_headers)).status_code == 401

    assert (
        await client.post("/api/v1/auth/sessions/revoke-others", headers=second_headers)
    ).status_code == 200


async def test_legacy_access_token_without_sid_remains_compatible(client: AsyncClient, auth: dict):
    current = auth["Authorization"].removeprefix("Bearer ")
    decoded = decode_token(current, "access")
    assert decoded is not None
    user_id, version, _sid = decoded
    legacy = create_access_token(user_id, version)
    resp = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {legacy}"},
    )
    assert resp.status_code == 200


async def test_email_change_link_and_reuse(client: AsyncClient, auth: dict, monkeypatch):
    old_email = f"{uuid4().hex[:8]}@example.com"
    new_email = f"{uuid4().hex[:8]}@example.com"
    _user_id, _username, user_auth = await _create_ready_user(
        client, auth, prefix="email_change", email=old_email,
    )
    captured = _capture_account_email(monkeypatch)
    resp = await client.post(
        "/api/v1/auth/email-change",
        headers=user_auth,
        json={"current_password": "Init@12345x", "new_email": new_email.upper()},
    )
    assert resp.status_code == 202, resp.text
    assert captured[-1]["to"] == new_email
    token = _extract_token(captured[-1])
    assert (
        await client.post("/api/v1/auth/email-change/confirm", json={"token": token})
    ).status_code == 200
    assert (
        await client.post("/api/v1/auth/email-change/confirm", json={"token": token})
    ).status_code == 400
    me = (await client.get("/api/v1/auth/me", headers=user_auth)).json()
    assert me["email"] == new_email


async def test_password_reset_generic_response_and_confirmation(
    client: AsyncClient, auth: dict, monkeypatch,
):
    email = f"{uuid4().hex[:8]}@example.com"
    _user_id, username, _user_auth = await _create_ready_user(
        client, auth, prefix="forgot", email=email,
    )
    captured = _capture_account_email(monkeypatch)
    unknown = await client.post(
        "/api/v1/auth/password-reset/request", json={"email": f"{uuid4().hex}@example.com"},
    )
    assert unknown.status_code == 202
    assert captured == []

    for _ in range(3):
        resp = await client.post("/api/v1/auth/password-reset/request", json={"email": email})
        assert resp.status_code == 202
    assert len(captured) == 3
    token = _extract_token(captured[-1])
    resp = await client.post(
        "/api/v1/auth/password-reset/confirm",
        json={"token": token, "new_password": "Forgot@12345"},
    )
    assert resp.status_code == 200, resp.text
    assert (
        await client.post(
            "/api/v1/auth/login", data={"username": username, "password": "Forgot@12345"},
        )
    ).status_code == 200
