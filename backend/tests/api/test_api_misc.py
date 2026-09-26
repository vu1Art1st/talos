"""API 集成测试：横切关注点（令牌 / 审计 / 通知 / CVSS / 影响URL）。

横切关注点：refresh token 轮换与滑动过期、审计日志与 /meta
字典、通知渠道、漏洞 CVSS 字段、影响URL 录入约束。

原 tests/test_api.py（4626 行单体）按领域拆分而来：用例源码逐字未改，
仅按领域重新归位；共享夹具见 tests/conftest.py，共享 helper 见 tests/api/_helpers.py。
"""
import pytest
from httpx import AsyncClient

from _helpers import _many_urls

pytestmark = pytest.mark.asyncio(loop_scope="session")


# ---------- refresh token 空闲 24h 滑动过期 ----------
async def test_refresh_rotation_and_expiry(client: AsyncClient):
    """refresh 轮换下发新令牌对（滑动重置）；过期 refresh 被拒绝。"""
    resp = await client.post(
        "/api/v1/auth/login", data={"username": "admin", "password": "admin123"}
    )
    refresh = resp.json()["refresh_token"]

    # 轮换：新 access 可用，且再次下发新 refresh（计时重置的实现）
    resp = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh})
    assert resp.status_code == 200, resp.text
    pair = resp.json()
    me = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {pair['access_token']}"})
    assert me.status_code == 200
    resp = await client.post("/api/v1/auth/refresh", json={"refresh_token": pair["refresh_token"]})
    assert resp.status_code == 200

    # 空闲超 24 小时的 refresh（构造已过期令牌）被拒绝
    from datetime import timedelta

    from app.core import security

    expired = security._create_token("1", "refresh", timedelta(hours=-1), 0)
    resp = await client.post("/api/v1/auth/refresh", json={"refresh_token": expired})
    assert resp.status_code == 401

# ---------- F7 审计 ----------
async def test_audit_login_and_operation(client: AsyncClient, auth: dict):
    """登录成败写审计；敏感操作（建漏洞）写审计；查询端点按类目过滤。"""
    # 失败登录 → login_failure
    await client.post("/api/v1/auth/login", data={"username": "admin", "password": "nope"})

    resp = await client.get("/api/v1/audit/logs", headers=auth, params={"category": "login", "size": 50})
    assert resp.status_code == 200, resp.text
    logs = resp.json()
    assert logs["total"] >= 1
    actions = {i["action"] for i in logs["items"]}
    assert "login_success" in actions and "login_failure" in actions
    sample = logs["items"][0]
    assert sample["username"] and sample["ip"] != "" and sample["create_time"]
    # 展示名：admin 设置了姓名，登录成功记录应返回 realname
    succ = next(i for i in logs["items"] if i["action"] == "login_success")
    assert succ["realname"] == "管理员"

    # 操作日志：建漏洞 → vuln_create
    await client.post("/api/v1/vulns", headers=auth, json={"title": "审计测试漏洞", "level": 30})
    resp = await client.get("/api/v1/audit/logs", headers=auth, params={"category": "operation", "size": 50})
    items = resp.json()["items"]
    actions = {i["action"] for i in items}
    assert "vuln_create" in actions
    # 操作人姓名解析（user_id 命中优先）
    op = next(i for i in items if i["action"] == "vuln_create")
    assert op["realname"] == "管理员"

    # 筛选：按动作精确定位
    resp = await client.get("/api/v1/audit/logs", headers=auth, params={"action": "login_failure"})
    assert all(i["action"] == "login_failure" for i in resp.json()["items"])

async def test_meta_audit_and_notify_dicts(client: AsyncClient, auth: dict):
    resp = await client.get("/api/v1/meta", headers=auth)
    meta = resp.json()
    assert meta["audit_actions"]["login_success"] == "登录成功"
    assert set(meta["notify_channel_types"]) == {"wecom", "dingtalk", "email"}
    assert "retest_completed" in meta["notify_events"]

# ---------- F3 通知渠道 ----------
async def test_notify_channel_crud_and_validation(client: AsyncClient, auth: dict):
    # 类型非法 / webhook 地址缺失被拒
    resp = await client.post(
        "/api/v1/notify-channels", headers=auth,
        json={"name": "坏类型", "type": "sms", "config": {}, "events": ["vuln_created"]},
    )
    assert resp.status_code == 422
    resp = await client.post(
        "/api/v1/notify-channels", headers=auth,
        json={"name": "缺地址", "type": "wecom", "config": {}, "events": ["vuln_created"]},
    )
    assert resp.status_code == 422
    # 出站目标必须是公网地址（审计 TALOS-2026-003）：内网/元数据地址与无法解析的主机一律拒绝
    resp = await client.post(
        "/api/v1/notify-channels", headers=auth,
        json={
            "name": "内网地址", "type": "wecom",
            "config": {"url": "http://169.254.169.254/latest/meta-data/"},
            "events": ["vuln_created"],
        },
    )
    assert resp.status_code == 422, resp.text
    resp = await client.post(
        "/api/v1/notify-channels", headers=auth,
        json={
            "name": "不可解析主机", "type": "wecom",
            "config": {"url": "https://qyapi.example.com/hook"},
            "events": ["vuln_created"],
        },
    )
    assert resp.status_code == 422, resp.text
    # 邮箱渠道缺收件人被拒
    resp = await client.post(
        "/api/v1/notify-channels", headers=auth,
        json={"name": "缺收件人", "type": "email", "config": {}, "events": ["vuln_created"]},
    )
    assert resp.status_code == 422

    # 正常创建 / 编辑 / 测试发送 / 删除（webhook 地址用公网 IP 字面量：不依赖 DNS，判定确定）
    resp = await client.post(
        "/api/v1/notify-channels", headers=auth,
        json={
            "name": "安全群机器人", "type": "wecom",
            "config": {"url": "https://1.1.1.1/hook"},
            "events": ["vuln_created", "retest_completed"], "is_active": True,
        },
    )
    assert resp.status_code == 200, resp.text
    channel = resp.json()
    assert channel["events"] == ["vuln_created", "retest_completed"]

    resp = await client.put(
        f"/api/v1/notify-channels/{channel['id']}", headers=auth,
        json={
            "name": "安全群机器人", "type": "wecom",
            "config": {"url": "https://1.1.1.1/hook2"},
            "events": ["vuln_transition"], "is_active": False,
        },
    )
    assert resp.status_code == 200
    assert resp.json()["is_active"] is False

    resp = await client.post(f"/api/v1/notify-channels/{channel['id']}/test", headers=auth)
    assert resp.status_code == 200
    resp = await client.delete(f"/api/v1/notify-channels/{channel['id']}", headers=auth)
    assert resp.status_code == 200

async def test_notify_emit_on_vuln_created(client: AsyncClient, auth: dict, monkeypatch):
    """漏洞创建事件触发渠道分发（monkeypatch dispatch 捕获，不出站）。

    锁定 P1-3 的投递记录契约：任务参数是**投递记录 ID**（成功后重投短路、状态可查询），
    且 dispatch 带投递级 `job_id=f"notify:{id}"`（重复入队被 arq 拒绝）。
    """
    calls: list[tuple] = []

    async def fake_dispatch(app, func_name, *args, **kwargs):
        calls.append((func_name, args, kwargs))

    import app.services.notify_service as notify_service

    monkeypatch.setattr(notify_service, "dispatch", fake_dispatch)

    resp = await client.post(
        "/api/v1/notify-channels", headers=auth,
        json={
            "name": "邮件渠道", "type": "email",
            "config": {"recipients": ["sec@example.com"]},
            "events": ["vuln_created"], "is_active": True,
        },
    )
    assert resp.status_code == 200

    resp = await client.post("/api/v1/vulns", headers=auth, json={"title": "通知触发漏洞", "level": 30})
    assert resp.status_code == 200

    notify_calls = [c for c in calls if c[0] == "send_notify_task"]
    assert notify_calls, "漏洞创建应触发通知分发"
    _func, args, kwargs = notify_calls[0]
    delivery_id = args[0]
    assert isinstance(delivery_id, int), "通知任务参数应为投递记录 ID"
    assert kwargs.get("job_id") == f"notify:{delivery_id}"

    # 投递记录可查询：目标摘要脱敏（仅域名），正文含事件标题
    resp = await client.get(
        "/api/v1/notify-channels/deliveries", headers=auth,
        params={"event": "vuln_created"},
    )
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert items and items[0]["status"] == "pending"
    assert "example.com" in items[0]["target"]
    assert "sec@" not in items[0]["target"]

# ---------- F4 CVSS ----------
async def test_vuln_cvss_fields(client: AsyncClient, auth: dict):
    vector = "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H"
    resp = await client.post(
        "/api/v1/vulns", headers=auth,
        json={"title": "CVSS评分漏洞", "level": 10, "score": 9.8, "cvss_vector": vector},
    )
    assert resp.status_code == 200, resp.text
    vul = resp.json()
    assert vul["score"] == 9.8
    assert vul["cvss_vector"] == vector

    # 编辑改分
    resp = await client.put(
        f"/api/v1/vulns/{vul['id']}", headers=auth,
        json={"title": "CVSS评分漏洞", "level": 10, "score": 5.3,
              "cvss_vector": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:L/I:N/A:N"},
    )
    assert resp.status_code == 200
    assert resp.json()["score"] == 5.3

async def test_affected_url_multi_value_within_limits(client: AsyncClient, auth: dict):
    """回归：影响URL 录入 20/50/100 条（总远超前 varchar(512)）不再 500，且读回一致。

    旧实现该列是 varchar(512)，PostgreSQL 在 flush 时抛 StringDataRightTruncation → 兜底 500；
    改用 TEXT 后以「写入成功 + 读回一致」固化行为（测试库即为 PG，长度约束真实生效）。
    """
    # 20 条：单漏洞录入
    urls20 = _many_urls(20)
    resp = await client.post(
        "/api/v1/vulns", headers=auth,
        json={"title": "多URL回归20", "level": 20, "affected_url": "\n".join(urls20)},
    )
    assert resp.status_code == 200, resp.text
    vul_id = resp.json()["id"]
    assert resp.json()["affected_url"] == "\n".join(urls20)

    resp = await client.get(f"/api/v1/vulns/{vul_id}", headers=auth)
    assert resp.status_code == 200, resp.text
    assert resp.json()["affected_url"] == "\n".join(urls20)

    # 50 条：批量提交入口
    urls50 = _many_urls(50)
    resp = await client.post(
        "/api/v1/vulns/batch", headers=auth,
        json={"asset_ids": [], "vulns": [
            {"title": "多URL回归50", "level": 30, "affected_url": "\n".join(urls50)},
        ]},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()[0]["affected_url"] == "\n".join(urls50)

    # 100 条（上限）：编辑入口
    urls100 = _many_urls(100)
    resp = await client.put(
        f"/api/v1/vulns/{vul_id}", headers=auth,
        json={"title": "多URL回归20", "level": 20, "affected_url": "\n".join(urls100)},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["affected_url"] == "\n".join(urls100)
    assert len(resp.json()["affected_url"]) > 512  # 远超旧列长

async def test_affected_url_input_normalized_on_write(client: AsyncClient, auth: dict):
    """分号/空白/重复项在写入时统一规范化：切分、trim、去空、去重保序。"""
    resp = await client.post(
        "/api/v1/vulns", headers=auth,
        json={
            "title": "多URL规范化", "level": 30,
            "affected_url": " https://b.example.com/1 ; https://a.example.com/2 \n"
                            "https://b.example.com/1\n\n；\n",
        },
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["affected_url"] == "https://b.example.com/1\nhttps://a.example.com/2"

async def test_affected_url_over_limit_returns_422_with_readable_detail(client: AsyncClient, auth: dict):
    """超限（条数/单条长度/非法字符）返回 422 且透出可读中文，而非通用 500/泛化提示。"""
    resp = await client.post(
        "/api/v1/vulns", headers=auth,
        json={"title": "超限101条", "level": 30, "affected_url": "\n".join(_many_urls(101))},
    )
    assert resp.status_code == 422, resp.text
    assert "最多 100 条" in resp.json()["detail"]

    too_long = "https://many.example.com/" + "a" * 2048
    resp = await client.post(
        "/api/v1/vulns", headers=auth,
        json={"title": "单条超长", "level": 30, "affected_url": too_long},
    )
    assert resp.status_code == 422, resp.text
    assert "超出上限 2048 字符" in resp.json()["detail"]

    resp = await client.post(
        "/api/v1/vulns", headers=auth,
        json={"title": "含空格", "level": 30, "affected_url": "https://a.example.com/1 描述"},
    )
    assert resp.status_code == 422, resp.text
    assert "含空格或非法字符" in resp.json()["detail"]

    # 编辑入口同口径
    resp = await client.post(
        "/api/v1/vulns", headers=auth, json={"title": "编辑超限", "level": 30},
    )
    assert resp.status_code == 200, resp.text
    resp = await client.put(
        f"/api/v1/vulns/{resp.json()['id']}", headers=auth,
        json={"title": "编辑超限", "level": 30, "affected_url": "\n".join(_many_urls(101))},
    )
    assert resp.status_code == 422, resp.text

async def test_import_record_affected_url_limits(client: AsyncClient, auth: dict):
    """导入结果修正页同一口径：长 URL 可保存，超限 422 且文案可读。"""
    from app.db import async_session_maker
    from app.models import ImportBatch, ImportRecord

    async with async_session_maker() as session:
        batch = ImportBatch(filename="影响URL上限测试.docx", file_path="")
        session.add(batch)
        await session.flush()
        record = ImportRecord(batch_id=batch.id, seq=1, title="导入记录URL上限")
        session.add(record)
        await session.commit()
        record_id = record.id

    urls100 = _many_urls(100)
    resp = await client.put(
        f"/api/v1/imports/records/{record_id}", headers=auth,
        json={"affected_url": "；".join(urls100)},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["affected_url"] == "\n".join(urls100)

    resp = await client.put(
        f"/api/v1/imports/records/{record_id}", headers=auth,
        json={"affected_url": "\n".join(_many_urls(101))},
    )
    assert resp.status_code == 422, resp.text
    assert "最多 100 条" in resp.json()["detail"]
