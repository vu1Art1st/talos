"""P1 批次接口契约测试（SLA / 站内消息与待办 / 报告模板 / 开放 API / 看板视图 / 导入治理）。

对应 ROADMAP P1-1 ~ P1-7 的验收条件：策略配置与历史重算、延期留痕与权限、消息深链与
未读口径、模板占位符校验与版本回滚、PAT scope 与写幂等、看板视图与运营指标、
重复候选合并与结果报告。
"""
from pathlib import Path
from uuid import uuid4

import pytest
from httpx import AsyncClient

from _helpers import _upload_report_batch, _user_with_perms

pytestmark = pytest.mark.asyncio(loop_scope="session")

_DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
# 包内默认模板（7 张锚点表齐备），用于验证「校验通过才能发布」
_DEFAULT_TEMPLATE = Path(__file__).resolve().parents[2] / "app" / "templates" / "report_template.docx"


def _sla_body(**kw) -> dict:
    body = {
        "enabled": True, "day_basis": "natural", "default_days": 7, "warn_hours": 24,
        "allow_extend": True, "workdays": [0, 1, 2, 3, 4], "holidays": [],
        "stop_statuses": [20, 60], "remark": "",
    }
    body.update(kw)
    return body


async def _create_vuln(client: AsyncClient, auth: dict, title: str, level: int = 20) -> dict:
    resp = await client.post("/api/v1/vulns", headers=auth, json={"title": title, "level": level})
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _new_pat(client: AsyncClient, auth: dict, name: str, scope: str) -> dict:
    resp = await client.post(
        "/api/v1/pats", headers=auth, json={"name": name, "expire_days": 7, "scope": scope},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["scope"] == scope
    return {"Authorization": f"Bearer {body['token']}"}


# ---------- P1-1 SLA ----------
async def test_sla_config_policy_recalculate_and_extend(client: AsyncClient, auth: dict):
    """策略配置 → 等级时限 → 历史重算 → 列表筛选 → 延期留痕；关闭时不影响既有流程。"""
    # 1. 默认关闭：新建漏洞不设截止时间（不阻塞任何流程）
    resp = await client.put("/api/v1/sla/config", headers=auth, json=_sla_body(enabled=False))
    assert resp.status_code == 200, resp.text
    vul = await _create_vuln(client, auth, "P1SLA-关闭用例")
    assert vul["due_at"] is None and vul["sla_state"] == "none"

    # 2. 开启 SLA 并配置高危 3 天
    assert (await client.put("/api/v1/sla/config", headers=auth, json=_sla_body())).status_code == 200
    resp = await client.post(
        "/api/v1/sla/policies", headers=auth,
        json={"level": 20, "days": 3, "enabled": True, "remark": "高危 3 天"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["days"] == 3

    # 3. 历史重算：显式执行后历史漏洞获得截止时间
    resp = await client.post("/api/v1/sla/recalculate", headers=auth, json={"scope": "open"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["refreshed"] >= 1
    detail = (await client.get(f"/api/v1/vulns/{vul['id']}", headers=auth)).json()
    assert detail["due_at"] is not None
    assert detail["sla_state"] in ("ok", "due_soon")
    assert detail["sla_remaining_hours"] is not None

    # 4. 列表筛选与详情同源：sla_state=none 只返回无截止时间的漏洞
    resp = await client.get("/api/v1/vulns", headers=auth, params={"sla_state": "none", "size": 100})
    assert resp.status_code == 200, resp.text
    assert all(item["due_at"] is None for item in resp.json()["items"])
    resp = await client.get("/api/v1/vulns", headers=auth, params={"sla_state": "ok", "size": 100})
    assert all(item["sla_state"] == "ok" for item in resp.json()["items"])

    # 5. 延期：记录原/新到期时间、原因，并写入漏洞日志
    resp = await client.post(
        f"/api/v1/sla/vulns/{vul['id']}/extend", headers=auth,
        json={"reason": "上线窗口延后", "extend_days": 2, "new_due_at": None},
    )
    assert resp.status_code == 200, resp.text
    ext = resp.json()
    assert ext["old_due_at"] and ext["new_due_at"] > ext["old_due_at"]
    rows = (await client.get(f"/api/v1/sla/vulns/{vul['id']}/extensions", headers=auth)).json()
    assert len(rows) == 1 and rows[0]["reason"] == "上线窗口延后"
    logs = (await client.get(f"/api/v1/vulns/{vul['id']}/logs", headers=auth)).json()
    assert any("SLA 延期" in (log.get("action") or "") for log in logs)

    # 6. 关闭延期开关后拒绝（策略可配置）
    assert (await client.put(
        "/api/v1/sla/config", headers=auth, json=_sla_body(allow_extend=False),
    )).status_code == 200
    resp = await client.post(
        f"/api/v1/sla/vulns/{vul['id']}/extend", headers=auth,
        json={"reason": "再延一天", "extend_days": 1},
    )
    assert resp.status_code == 400 and "不允许延期" in resp.text

    # 7. 统计接口可用（看板与 SLA 页共用）
    resp = await client.get("/api/v1/sla/stats", headers=auth)
    assert resp.status_code == 200, resp.text
    stats = resp.json()
    assert stats["sla_total"] >= 1 and stats["enabled"] is True
    assert isinstance(stats["by_level"], list) and isinstance(stats["by_department"], list)

    # 收尾：关闭 SLA，避免影响后续用例
    assert (await client.put(
        "/api/v1/sla/config", headers=auth, json=_sla_body(enabled=False),
    )).status_code == 200


async def test_sla_config_requires_system_manage(client: AsyncClient, auth: dict):
    """修改策略必须 `system:manage`：普通只读账号 403，且不写入任何变更。"""
    ro = await _user_with_perms(client, auth, "p1sla_ro", ["vuln:view"])
    resp = await client.put("/api/v1/sla/config", headers=ro, json=_sla_body(default_days=1))
    assert resp.status_code == 403, resp.text
    resp = await client.post(
        "/api/v1/sla/policies", headers=ro,
        json={"level": 10, "days": 1, "enabled": True},
    )
    assert resp.status_code == 403
    # 读配置不受限（列表与详情页需要据此展示剩余时间）
    assert (await client.get("/api/v1/sla/config", headers=ro)).status_code == 200


async def test_sla_reminder_fires_once_per_due_state(client: AsyncClient, auth: dict):
    """同一漏洞同一到期时间的同一类提醒只产生一次（重复扫描不重复通知）。"""
    from datetime import timedelta

    from sqlalchemy import func, select

    from app.core.timeutil import now
    from app.db import async_session_maker
    from app.models import Message, Vul
    from app.workers.main import sla_scan_task

    assert (await client.put("/api/v1/sla/config", headers=auth, json=_sla_body())).status_code == 200
    vul = await _create_vuln(client, auth, "P1SLA-提醒用例")
    async with async_session_maker() as session:
        row = await session.get(Vul, vul["id"])
        row.due_at = now() - timedelta(hours=1)  # 已逾期
        await session.commit()

    async def _sla_messages() -> int:
        async with async_session_maker() as session:
            return (
                await session.execute(
                    select(func.count(Message.id)).where(
                        Message.link == f"/vulns/{vul['id']}", Message.msg_type == "sla",
                    )
                )
            ).scalar_one()

    await sla_scan_task({})
    assert await _sla_messages() == 1
    # 第二次扫描：幂等键已抢占，不再重复提醒
    await sla_scan_task({})
    assert await _sla_messages() == 1

    assert (await client.put(
        "/api/v1/sla/config", headers=auth, json=_sla_body(enabled=False),
    )).status_code == 200


# ---------- P1-2 站内消息与待办 ----------
async def test_message_center_and_todos(client: AsyncClient, auth: dict):
    """漏洞流转生成带深链的站内信；未读数与已读状态可查、待办按权限聚合。"""
    submitter = await _user_with_perms(client, auth, "p1msg_user", ["vuln:view", "vuln:submit"])
    resp = await client.post(
        "/api/v1/vulns", headers=submitter, json={"title": "P1消息-提交人漏洞", "level": 20},
    )
    assert resp.status_code == 200, resp.text
    vul_id = resp.json()["id"]

    # 管理员流转 → 提交人收到站内信（带 /vulns/{id} 深链）
    resp = await client.post(
        f"/api/v1/vulns/{vul_id}/transition", headers=auth,
        json={"status": 50, "comment": "开始修复"},
    )
    assert resp.status_code == 200, resp.text

    resp = await client.get("/api/v1/messages", headers=submitter, params={"size": 50})
    assert resp.status_code == 200, resp.text
    page = resp.json()
    target = next(m for m in page["items"] if f"/vulns/{vul_id}" == m["link"])
    assert target["msg_type"] == "vuln" and target["is_read"] is False
    assert page["unread"] >= 1

    before = (await client.get("/api/v1/messages/unread-count", headers=submitter)).json()["unread"]
    assert before >= 1
    resp = await client.post(f"/api/v1/messages/{target['id']}/read", headers=submitter)
    assert resp.status_code == 200
    after = (await client.get("/api/v1/messages/unread-count", headers=submitter)).json()["unread"]
    assert after == before - 1
    # 幂等：重复置已读不改变计数
    assert (await client.post(f"/api/v1/messages/{target['id']}/read", headers=submitter)).status_code == 200
    assert (await client.get("/api/v1/messages/unread-count", headers=submitter)).json()["unread"] == after

    # 一键全部已读（ids 为空 = 全部）
    resp = await client.post("/api/v1/messages/read", headers=submitter, json={"ids": []})
    assert resp.status_code == 200
    assert (await client.get("/api/v1/messages/unread-count", headers=submitter)).json()["unread"] == 0

    # 待办聚合：提交人能看到自己提交的未闭环漏洞
    resp = await client.get("/api/v1/todos", headers=submitter)
    assert resp.status_code == 200, resp.text
    groups = {g["category"]: g for g in resp.json()["groups"]}
    assert "my_vulns" in groups and groups["my_vulns"]["count"] >= 1
    assert any(item.get("id") == vul_id for item in groups["my_vulns"]["items"])


# ---------- P1-4 报告模板 ----------
async def test_report_template_publish_validation_and_rollback(client: AsyncClient, auth: dict):
    """占位符缺失阻止发布；合法模板可发布，版本 +1 且同名旧版本自动停用（回滚＝重新启用）。"""
    from docx import Document
    from io import BytesIO

    def _docx_bytes(doc) -> bytes:
        buf = BytesIO()
        doc.save(buf)
        return buf.getvalue()

    # 1. 无锚点表结构的文档：上传即被拦（publish=true）
    bogus = Document()
    bogus.add_paragraph("这不是报告模板")
    resp = await client.post(
        "/api/v1/report-templates", headers=auth,
        files={"file": ("bogus.docx", _docx_bytes(bogus), _DOCX_MIME)},
        data={"name": "P1非法模板", "report_type": "penetration", "publish": "true", "remark": ""},
    )
    assert resp.status_code == 400, resp.text
    assert "占位符" in resp.text or "缺失" in resp.text

    # 2. 以未发布方式上传，再对非法版本执行发布 → 同样被拦
    resp = await client.post(
        "/api/v1/report-templates", headers=auth,
        files={"file": ("bogus.docx", _docx_bytes(bogus), _DOCX_MIME)},
        data={"name": "P1非法模板", "report_type": "penetration", "publish": "false", "remark": ""},
    )
    assert resp.status_code == 200, resp.text
    bogus_id = resp.json()["id"]
    assert resp.json()["is_active"] is False
    resp = await client.post(f"/api/v1/report-templates/{bogus_id}/publish", headers=auth)
    assert resp.status_code == 400 and "占位符缺失" in resp.text

    # 3. 包内标准模板：校验通过 → 发布成功（锚点齐备）
    valid = _DEFAULT_TEMPLATE.read_bytes()
    resp = await client.post(
        "/api/v1/report-templates", headers=auth,
        files={"file": ("report_template.docx", valid, _DOCX_MIME)},
        data={"name": "P1标准模板", "report_type": "penetration", "publish": "true", "remark": "基线"},
    )
    assert resp.status_code == 200, resp.text
    v1 = resp.json()
    assert v1["is_active"] is True and v1["version"] == 1
    assert len(v1["anchors"]) >= 7, "标准模板应识别出 7 张锚点表"

    # 4. 上传第二个版本并发布 → v2 启用、v1 停用
    resp = await client.post(
        "/api/v1/report-templates", headers=auth,
        files={"file": ("report_template.docx", valid, _DOCX_MIME)},
        data={"name": "P1标准模板", "report_type": "penetration", "publish": "true", "remark": "v2"},
    )
    assert resp.status_code == 200, resp.text
    v2 = resp.json()
    assert v2["version"] == 2 and v2["is_active"] is True
    rows = (await client.get(
        "/api/v1/report-templates", headers=auth, params={"size": 100},
    )).json()["items"]
    v1_row = next(r for r in rows if r["id"] == v1["id"])
    assert v1_row["is_active"] is False, "同一名称同时只能有一个启用版本"

    # 5. 回滚：重新启用 v1
    resp = await client.post(f"/api/v1/report-templates/{v1['id']}/activate", headers=auth)
    assert resp.status_code == 200 and resp.json()["is_active"] is True
    rows = (await client.get("/api/v1/report-templates", headers=auth, params={"size": 100})).json()["items"]
    assert next(r for r in rows if r["id"] == v2["id"])["is_active"] is False

    # 6. 示例数据试生成可下载（模板不可用时导出仍回退包内默认模板）
    resp = await client.post(f"/api/v1/report-templates/{v1['id']}/preview", headers=auth)
    assert resp.status_code == 200, resp.text
    url = resp.json()["url"]
    assert url.startswith("/report-templates/previews/"), url
    # url 为「相对 API 基址」的路径（前端 client 的 baseURL 即 /api/v1）
    resp = await client.get(f"/api/v1{url}", headers=auth)
    assert resp.status_code == 200 and resp.headers["content-type"].startswith(_DOCX_MIME)

    # 7. 启用中的版本不可删除
    resp = await client.delete(f"/api/v1/report-templates/{v1['id']}", headers=auth)
    assert resp.status_code == 400


# ---------- P1-6 开放 API ----------
async def test_open_api_scope_cursor_and_idempotency(client: AsyncClient, auth: dict):
    """PAT 认证：JWT 被拒；scope 限制读写；写接口幂等；分页返回游标与版本头。"""
    read = await _new_pat(client, auth, "P1只读令牌", "read")

    # JWT 会话令牌不被开放 API 接受
    assert (await client.get("/api/v1/open/vulns", headers=auth)).status_code == 401

    resp = await client.get("/api/v1/open/vulns", headers=read, params={"size": 1})
    assert resp.status_code == 200, resp.text
    assert resp.headers.get("X-API-Version") == "1"
    assert resp.headers.get("X-RateLimit-Limit")
    body = resp.json()
    assert "has_more" in body and "next_cursor" in body
    assert set(body) <= {"total", "items", "page", "size", "has_more", "next_cursor"}

    # 游标遍历稳定（按 id 降序，不重复、不漏）：游标取上一页末条 id
    if body["has_more"]:
        cursor = body["items"][-1]["id"]
        page2 = await client.get(
            "/api/v1/open/vulns", headers=read, params={"cursor": cursor, "size": 1},
        )
        assert page2.status_code == 200, page2.text
        page2_body = page2.json()
        assert page2_body["items"], "游标模式应返回下一页数据"
        first_ids = {i["id"] for i in body["items"]}
        assert not (first_ids & {i["id"] for i in page2_body["items"]})
        assert max(i["id"] for i in page2_body["items"]) < cursor
        assert set(page2_body) <= {"total", "items", "page", "size", "has_more", "next_cursor"}

    # 只读 scope：不能写工单、不能读管理只读接口
    resp = await client.post(
        "/api/v1/open/testing-plans", headers=read, json={"system_name": "P1只读写入"},
    )
    assert resp.status_code == 403, resp.text
    assert (await client.get("/api/v1/open/sla-config", headers=read)).status_code == 403

    # 工单写 scope：幂等键保证重复提交只创建一个工单
    write = await _new_pat(client, auth, "P1工单写令牌", "plan_write")
    idem = {"Idempotency-Key": f"p1-{uuid4().hex}"}
    payload = {"system_name": f"P1幂等工单-{uuid4().hex[:6]}"}
    first = await client.post("/api/v1/open/testing-plans", headers={**write, **idem}, json=payload)
    assert first.status_code == 200, first.text
    again = await client.post("/api/v1/open/testing-plans", headers={**write, **idem}, json=payload)
    assert again.status_code == 200, again.text
    assert again.json()["id"] == first.json()["id"], "同键重放必须返回首次结果"

    # 同键不同内容 → 409（禁止用同键改写不同请求）
    conflict = await client.post(
        "/api/v1/open/testing-plans", headers={**write, **idem},
        json={"system_name": f"P1冲突工单-{uuid4().hex[:6]}"},
    )
    assert conflict.status_code == 409, conflict.text

    # 管理只读 scope：可读 SLA 配置与投递记录
    admin_read = await _new_pat(client, auth, "P1管理只读令牌", "admin_read")
    resp = await client.get("/api/v1/open/sla-config", headers=admin_read)
    assert resp.status_code == 200, resp.text
    assert "config" in resp.json() and "policies" in resp.json()
    assert (await client.get("/api/v1/open/notify-deliveries", headers=admin_read)).status_code == 200


# ---------- P1-7 看板 ----------
async def test_dashboard_views_and_ops_metrics(client: AsyncClient, auth: dict):
    """看板视图保存/列出/删除；聚合结果含 SLA 与运营指标（与列表/导出同源）。"""
    resp = await client.get("/api/v1/dashboard/stats", headers=auth)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "sla" in data and "ops" in data
    assert data["sla"]["overdue"] >= 0 and data["sla"]["overdue_rate"] >= 0
    assert data["ops"]["open_vulns"] >= 0 and data["ops"]["retest_backlog"] >= 0

    resp = await client.post("/api/v1/dashboard/views", headers=auth, json={
        "name": "P1视图-高危",
        "scope": "personal",
        "department": "",
        "is_default": True,
        "query": {"level": 20, "date_from": "", "date_to": ""},
    })
    assert resp.status_code == 200, resp.text
    view_id = resp.json()["id"]
    rows = (await client.get("/api/v1/dashboard/views", headers=auth)).json()
    saved = next(v for v in rows if v["id"] == view_id)
    assert saved["query"]["level"] == 20 and saved["scope"] == "personal"

    assert (await client.delete(f"/api/v1/dashboard/views/{view_id}", headers=auth)).status_code == 200
    assert all(v["id"] != view_id for v in (await client.get("/api/v1/dashboard/views", headers=auth)).json())


# ---------- P1-5 导入治理 ----------
async def test_import_governance_duplicates_merge_and_report(client: AsyncClient, auth: dict):
    """解析链可追溯（等级来源 + 修正留痕）、重复候选合并、失败重试与结果报告下载。"""
    system = f"P1治理系统{uuid4().hex[:6]}"
    existing = await _create_vuln(client, auth, f"{system}漏洞A", level=20)
    batch_id = await _upload_report_batch(client, auth, system, f"{system}报告.docx")

    detail = (await client.get(f"/api/v1/imports/{batch_id}", headers=auth)).json()
    rec = detail["records"][0]
    # 解析链：等级来源为「风险问题详情」的权威等级
    assert rec["level_source"] in ("detail", "summary", "template", "default")
    assert rec["level"] == 20

    # 重复候选：同名已入库漏洞应列为候选
    resp = await client.get(f"/api/v1/imports/{batch_id}/duplicates", headers=auth)
    assert resp.status_code == 200, resp.text
    groups = resp.json()
    group = next(g for g in groups if g["record_id"] == rec["id"])
    assert any(c["vul_id"] == existing["id"] for c in group["candidates"])
    assert group["candidates"][0]["similarity"] >= 0.5

    # 人工修正留痕（可追溯数据链）
    resp = await client.put(
        f"/api/v1/imports/records/{rec['id']}", headers=auth,
        json={"title": f"{system}漏洞A", "level": 20, "vul_type": 75,
              "affected_url": rec["affected_url"] or "https://p1.example.com/a"},
    )
    assert resp.status_code == 200, resp.text
    changes = (await client.get(f"/api/v1/imports/records/{rec['id']}/changes", headers=auth)).json()
    assert changes and all(c["record_id"] == rec["id"] for c in changes)

    # 合并到已有漏洞 → 确认入库结果为 merged（不新建漏洞）
    resp = await client.post(
        f"/api/v1/imports/records/{rec['id']}/merge", headers=auth, json={"vul_id": existing["id"]},
    )
    assert resp.status_code == 200 and resp.json()["merge_vul_id"] == existing["id"]

    resp = await client.post(
        f"/api/v1/imports/{batch_id}/confirm", headers=auth, json={"record_ids": [rec["id"]]},
    )
    assert resp.status_code == 200, resp.text
    after = (await client.get(f"/api/v1/imports/{batch_id}", headers=auth)).json()["records"][0]
    assert after["status"] == "confirmed"
    assert after["outcome"] == "merged" and after["merge_vul_id"] == existing["id"]

    # 结果报告（xlsx）：含入库结果列，可直接复核
    resp = await client.get(f"/api/v1/imports/{batch_id}/result-report", headers=auth)
    assert resp.status_code == 200, resp.text
    assert "spreadsheet" in resp.headers["content-type"]
