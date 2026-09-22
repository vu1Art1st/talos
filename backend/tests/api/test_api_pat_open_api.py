"""API 集成测试：个人访问令牌与开放 API。

个人访问令牌与开放 API：生命周期、过期拒绝、限流、开放工单读写。

原 tests/test_api.py（4626 行单体）按领域拆分而来：用例源码逐字未改，
仅按领域重新归位；共享夹具见 tests/conftest.py，共享 helper 见 tests/api/_helpers.py。
"""
import pytest
from httpx import AsyncClient

from _helpers import _login_ready

pytestmark = pytest.mark.asyncio(loop_scope="session")


# ---------- F6 PAT 与开放 API ----------
async def test_pat_lifecycle_and_open_api(client: AsyncClient, auth: dict):
    # 非法档位被拒
    resp = await client.post("/api/v1/pats", headers=auth, json={"name": "非法档位", "expire_days": 15})
    assert resp.status_code == 422

    # 创建：明文仅此一次返回
    resp = await client.post(
        "/api/v1/pats", headers=auth, json={"name": "看板令牌", "expire_days": 30}
    )
    assert resp.status_code == 200, resp.text
    pat = resp.json()
    assert pat["token"].startswith("tlp_") and pat["prefix"]
    pat_id, plaintext = pat["id"], pat["token"]

    # 列表不含明文
    resp = await client.get("/api/v1/pats", headers=auth)
    items = resp.json()["items"]
    assert all("token" not in i for i in items)
    assert any(i["id"] == pat_id and i["name"] == "看板令牌" for i in items)

    pat_headers = {"Authorization": f"Bearer {plaintext}"}
    # 开放 API：PAT 可查询漏洞与统计
    resp = await client.get("/api/v1/open/vulns", headers=pat_headers, params={"size": 5})
    assert resp.status_code == 200, resp.text
    assert "items" in resp.json() and "total" in resp.json()
    resp = await client.get("/api/v1/open/stats", headers=pat_headers)
    assert resp.status_code == 200, resp.text
    assert "total_vulns" in resp.json()

    # 认证边界：JWT 访问开放 API 被拒；PAT 访问站内端点被拒
    resp = await client.get("/api/v1/open/vulns", headers=auth)
    assert resp.status_code == 401
    resp = await client.get("/api/v1/vulns", headers=pat_headers)
    assert resp.status_code == 401

    # 吊销后 PAT 失效
    resp = await client.delete(f"/api/v1/pats/{pat_id}", headers=auth)
    assert resp.status_code == 200
    resp = await client.get("/api/v1/open/vulns", headers=pat_headers)
    assert resp.status_code == 401

async def test_pat_expired_rejected(client: AsyncClient, auth: dict):
    """过期 PAT 被拒绝（直接落库一条已过期令牌）。"""
    from datetime import timedelta

    from app.core.timeutil import now
    from app.db import async_session_maker
    from app.models import PersonalAccessToken

    from app.api.v1.pats import generate_pat

    token, token_hash, prefix = generate_pat()
    async with async_session_maker() as session:
        session.add(PersonalAccessToken(
            user_id=1, name="过期令牌", token_hash=token_hash, prefix=prefix,
            expires_at=now() - timedelta(minutes=1),
        ))
        await session.commit()

    resp = await client.get("/api/v1/open/vulns", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401
    assert "过期" in resp.json()["detail"]

async def test_pat_rate_limit(client: AsyncClient, auth: dict, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "PAT_RATE_LIMIT", 3)
    resp = await client.post("/api/v1/pats", headers=auth, json={"name": "限流令牌", "expire_days": 7})
    plaintext = resp.json()["token"]
    headers = {"Authorization": f"Bearer {plaintext}"}
    codes = [(await client.get("/api/v1/open/stats", headers=headers)).status_code for _ in range(4)]
    assert codes[:3] == [200, 200, 200]
    assert codes[3] == 429

async def test_open_api_plan_read(client: AsyncClient, auth: dict):
    """开放 API 工单查询：PAT 可读渗透测试工单与漏扫基线工单，JWT 与站内端点边界不变。"""
    resp = await client.post(
        "/api/v1/pats", headers=auth, json={"name": "工单只读令牌", "expire_days": 30},
    )
    pat = {"Authorization": f"Bearer {resp.json()['token']}"}

    # 列表与详情（先在站内造一条，保证有数据）
    created = await client.post(
        "/api/v1/testing-plans", headers=auth,
        json={"system_name": "开放API只读系统", "test_type": "渗透测试", "status": 10},
    )
    assert created.status_code == 200, created.text
    plan_id = created.json()["id"]

    resp = await client.get("/api/v1/open/testing-plans", headers=pat, params={"size": 5})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "total" in body and "items" in body

    resp = await client.get(f"/api/v1/open/testing-plans/{plan_id}", headers=pat)
    assert resp.status_code == 200, resp.text
    for key in ("id", "ticket_id", "testers", "vuls", "reports", "retest_rounds"):
        assert key in resp.json()

    # 筛选参数生效：按部门精确过滤
    resp = await client.get(
        "/api/v1/open/testing-plans", headers=pat, params={"search": "开放API只读系统"},
    )
    assert [p["id"] for p in resp.json()["items"]] == [plan_id]

    # 漏扫基线工单列表可读
    assert (await client.get("/api/v1/open/nonpen-plans", headers=pat)).status_code == 200

    # 认证边界：JWT 访问开放工单接口被拒；PAT 访问站内工单端点被拒；不存在 404
    assert (await client.get("/api/v1/open/testing-plans", headers=auth)).status_code == 401
    assert (await client.get("/api/v1/testing-plans", headers=pat)).status_code == 401
    assert (await client.get("/api/v1/open/testing-plans/999999", headers=pat)).status_code == 404
    assert (await client.get("/api/v1/open/nonpen-plans/999999", headers=pat)).status_code == 404

    # 分页参数越界 422
    assert (
        await client.get("/api/v1/open/testing-plans", headers=pat, params={"size": 500})
    ).status_code == 422

async def test_open_api_plan_write(client: AsyncClient, auth: dict):
    """开放 API 工单写入：创建 / 更新渗透测试工单与漏扫基线工单，写操作受 special:manage 约束。"""
    resp = await client.post(
        "/api/v1/pats", headers=auth, json={"name": "工单写入令牌", "expire_days": 30},
    )
    pat = {"Authorization": f"Bearer {resp.json()['token']}"}

    # 创建渗透测试工单（工单ID按需求接收日期自动生成）
    resp = await client.post(
        "/api/v1/open/testing-plans", headers=pat,
        json={
            "system_name": "开放API写入系统", "test_type": "渗透测试",
            "department": "研发一部", "receive_time": "2026-09-03", "status": 10,
        },
    )
    assert resp.status_code == 200, resp.text
    plan = resp.json()
    plan_id = plan["id"]
    assert plan["ticket_id"].startswith("20260903-")
    assert plan["department"] == "研发一部"

    # 全量更新：改部门 + 状态流转 10 → 20（未测试 → 初测中）
    update_body = {
        "system_name": "开放API写入系统", "test_type": "渗透测试", "department": "研发二部",
        "receive_time": "2026-09-03", "status": 20,
    }
    resp = await client.put(f"/api/v1/open/testing-plans/{plan_id}", headers=pat, json=update_body)
    assert resp.status_code == 200, resp.text
    assert resp.json()["department"] == "研发二部"
    assert resp.json()["status"] == 20

    # 非法状态流转 400（初测中 20 不能直接到复测完成 60）
    resp = await client.put(
        f"/api/v1/open/testing-plans/{plan_id}", headers=pat, json={**update_body, "status": 60},
    )
    assert resp.status_code == 400

    # 必填校验 422（system_name 为空）
    resp = await client.post(
        "/api/v1/open/testing-plans", headers=pat, json={"system_name": ""},
    )
    assert resp.status_code == 422

    # 更新不存在的工单 404
    resp = await client.put(
        "/api/v1/open/testing-plans/999999", headers=pat, json=update_body,
    )
    assert resp.status_code == 404

    # 漏扫基线工单：创建 + 更新（测试项勾选生效）
    resp = await client.post(
        "/api/v1/open/nonpen-plans", headers=pat,
        json={
            "system_name": "开放API漏扫系统", "department": "研发一部",
            "receive_time": "2026-09-03", "test_items": ["baseline", "host"],
        },
    )
    assert resp.status_code == 200, resp.text
    nonpen = resp.json()
    nonpen_id = nonpen["id"]
    assert nonpen["ticket_id"].startswith("20260903-")
    assert nonpen["items"]["baseline"]["status"] == "not_started"
    assert nonpen["items"]["web"]["status"] == "ignored"

    resp = await client.put(
        f"/api/v1/open/nonpen-plans/{nonpen_id}", headers=pat,
        json={
            "system_name": "开放API漏扫系统", "department": "研发二部",
            "receive_time": "2026-09-03", "test_items": ["web"],
        },
    )
    assert resp.status_code == 200, resp.text
    updated = resp.json()
    assert updated["department"] == "研发二部"
    # 仅合并勾选变化：web 由 ignored 变 not_started，baseline 取消勾选保留 ignored
    assert updated["items"]["web"]["status"] == "not_started"
    assert updated["items"]["baseline"]["status"] == "ignored"

    # 工单ID必须存在来源（无接收日期且未手动指定）→ 422
    resp = await client.post(
        "/api/v1/open/nonpen-plans", headers=pat, json={"system_name": "缺少工单ID来源"},
    )
    assert resp.status_code == 422

    # 无 special:manage 权限的账号，其令牌写操作 403（读仍放行）
    resp = await client.post(
        "/api/v1/roles", headers=auth,
        json={"name": "无专项写入权限", "permissions": ["vuln:submit"], "remark": ""},
    )
    role_id = resp.json()["id"]
    resp = await client.post(
        "/api/v1/users", headers=auth,
        json={"username": "open_api_writer", "password": "Writer@123", "realname": "开放API写入",
              "email": "", "phone": "", "is_active": True, "role_id": role_id},
    )
    assert resp.status_code == 200, resp.text
    weak_auth = await _login_ready(client, "open_api_writer", "Writer@123")
    resp = await client.post(
        "/api/v1/pats", headers=weak_auth, json={"name": "无权限令牌", "expire_days": 7},
    )
    weak_pat = {"Authorization": f"Bearer {resp.json()['token']}"}

    assert (await client.get("/api/v1/open/testing-plans", headers=weak_pat)).status_code == 200
    resp = await client.post(
        "/api/v1/open/testing-plans", headers=weak_pat, json={"system_name": "无权限创建"},
    )
    assert resp.status_code == 403
    assert "special:manage" in resp.json()["detail"]
    resp = await client.put(
        f"/api/v1/open/testing-plans/{plan_id}", headers=weak_pat, json=update_body,
    )
    assert resp.status_code == 403
