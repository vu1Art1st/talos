"""API 集成测试：认证 → 业务 CRUD → 状态机 → Word 导入 → 报告与导出全链路。"""
import asyncio
from io import BytesIO

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_health(client: AsyncClient):
    resp = await client.get("/api/health")
    assert resp.status_code == 200


async def test_login_and_me(client: AsyncClient, auth: dict):
    resp = await client.get("/api/v1/auth/me", headers=auth)
    assert resp.status_code == 200
    body = resp.json()
    assert body["username"] == "admin"

    bad = await client.post(
        "/api/v1/auth/login", data={"username": "admin", "password": "wrong"}
    )
    assert bad.status_code == 401


async def test_meta(client: AsyncClient, auth: dict):
    resp = await client.get("/api/v1/meta", headers=auth)
    assert resp.status_code == 200
    meta = resp.json()
    assert "vul_level" in meta and "vul_status" in meta


async def test_app_and_vuln_lifecycle(client: AsyncClient, auth: dict):
    # 建应用
    resp = await client.post(
        "/api/v1/apps", headers=auth,
        json={"name": "测试商城", "url": "https://shop.example.com"},
    )
    assert resp.status_code == 200, resp.text
    app_id = resp.json()["id"]

    # 建漏洞（待审核 10）
    resp = await client.post(
        "/api/v1/vulns", headers=auth,
        json={
            "title": "订单接口越权", "level": 20, "vul_type": 30,
            "affected_url": "https://shop.example.com/api/order",
            "description_html": "<p>横向越权读取他人订单</p>",
            "app_id": app_id,
        },
    )
    assert resp.status_code == 200, resp.text
    vul = resp.json()
    assert vul["status"] == 10
    vul_id = vul["id"]

    # 可用流转应包含 40（已确认）
    resp = await client.get(f"/api/v1/vulns/{vul_id}/transitions", headers=auth)
    assert 40 in [t["status"] for t in resp.json()]

    # 10 -> 40 审核通过，打 audit_time
    resp = await client.post(
        f"/api/v1/vulns/{vul_id}/transition", headers=auth,
        json={"status": 40, "comment": "确认存在"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == 40
    assert resp.json()["audit_time"] is not None

    # 非法流转 40 -> 55 应被拒绝
    resp = await client.post(
        f"/api/v1/vulns/{vul_id}/transition", headers=auth,
        json={"status": 55},
    )
    assert resp.status_code == 400

    # 日志包含创建与状态流转
    resp = await client.get(f"/api/v1/vulns/{vul_id}/logs", headers=auth)
    actions = [log["action"] for log in resp.json()]
    assert "创建漏洞" in actions
    assert len(actions) >= 2


async def _wait_batch(client: AsyncClient, auth: dict, batch_id: int) -> dict:
    for _ in range(50):
        resp = await client.get(f"/api/v1/imports/{batch_id}", headers=auth)
        assert resp.status_code == 200
        detail = resp.json()
        if detail["batch"]["status"] in ("parsed", "failed", "confirmed"):
            return detail
        await asyncio.sleep(0.2)
    raise AssertionError("导入批次解析超时")


async def test_word_import_flow(client: AsyncClient, auth: dict):
    # 下载官方模板作为上传样例
    resp = await client.get("/api/v1/imports/template", headers=auth)
    assert resp.status_code == 200
    docx_bytes = resp.content

    # 非 docx 拒绝
    resp = await client.post(
        "/api/v1/imports", headers=auth,
        files={"file": ("bad.txt", b"hello", "text/plain")},
    )
    assert resp.status_code == 400

    # 上传并等待后台解析（DISABLE_QUEUE 下进程内执行）
    resp = await client.post(
        "/api/v1/imports", headers=auth,
        files={"file": ("样例报告.docx", BytesIO(docx_bytes),
                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
    )
    assert resp.status_code == 200, resp.text
    batch_id = resp.json()["id"]

    detail = await _wait_batch(client, auth, batch_id)
    assert detail["batch"]["status"] == "parsed", detail
    records = detail["records"]
    assert len(records) == 1
    rec = records[0]
    assert rec["status"] == "parsed"
    assert rec["level"] == 20

    # 预览修正标题后确认入库
    resp = await client.put(
        f"/api/v1/imports/records/{rec['id']}", headers=auth,
        json={"title": "后台登录接口存在SQL注入(已确认)"},
    )
    assert resp.status_code == 200

    resp = await client.post(
        f"/api/v1/imports/{batch_id}/confirm", headers=auth,
        json={"record_ids": [rec["id"]]},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["created"] == 1

    # 入库漏洞 source=60(Word导入)
    resp = await client.get(
        "/api/v1/vulns", headers=auth, params={"search": "已确认"}
    )
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["source"] == 60


async def _wait_job(client: AsyncClient, auth: dict, report_id: int, job_id: int) -> dict:
    for _ in range(50):
        resp = await client.get(f"/api/v1/reports/{report_id}/exports", headers=auth)
        job = next(j for j in resp.json() if j["id"] == job_id)
        if job["status"] in ("done", "failed"):
            return job
        await asyncio.sleep(0.2)
    raise AssertionError("导出任务超时")


async def test_report_edit_and_export(client: AsyncClient, auth: dict):
    # 取已有漏洞生成报告
    resp = await client.get("/api/v1/vulns", headers=auth)
    vul_ids = [v["id"] for v in resp.json()["items"]][:2]
    assert vul_ids

    resp = await client.post(
        "/api/v1/reports/from-vulns", headers=auth,
        json={"title": "季度渗透测试报告", "vul_ids": vul_ids},
    )
    assert resp.status_code == 200, resp.text
    report = resp.json()
    assert len(report["sections"]) == len(vul_ids)
    report_id = report["id"]

    # 错误 version 保存应 409（乐观锁）
    save_body = {
        "title": "季度渗透测试报告 V2",
        "project_name": "商城安全测试",
        "summary_html": "<p>本次共发现两个高危漏洞。</p>",
        "version": report["version"] + 99,
        "sections": report["sections"],
    }
    resp = await client.put(f"/api/v1/reports/{report_id}", headers=auth, json=save_body)
    assert resp.status_code == 409

    # 正确 version 保存成功且版本 +1
    save_body["version"] = report["version"]
    resp = await client.put(f"/api/v1/reports/{report_id}", headers=auth, json=save_body)
    assert resp.status_code == 200, resp.text
    saved = resp.json()
    assert saved["version"] == report["version"] + 1
    assert saved["title"] == "季度渗透测试报告 V2"

    # 导出 docx（pdf 依赖 Gotenberg，容器环境验证）
    resp = await client.post(
        f"/api/v1/reports/{report_id}/export", headers=auth, json={"fmt": "docx"}
    )
    assert resp.status_code == 200, resp.text
    job_id = resp.json()["id"]

    job = await _wait_job(client, auth, report_id, job_id)
    assert job["status"] == "done", job

    resp = await client.get(f"/api/v1/reports/exports/{job_id}/download", headers=auth)
    assert resp.status_code == 200
    assert resp.content[:2] == b"PK"  # docx 是 zip 容器


async def test_dashboard(client: AsyncClient, auth: dict):
    resp = await client.get("/api/v1/dashboard/stats", headers=auth)
    assert resp.status_code == 200
    stats = resp.json()
    assert stats["total_vulns"] >= 2
    assert "by_level" in stats and "trend" in stats
    assert len(stats["trend"]) == 12


async def test_permission_denied(client: AsyncClient):
    resp = await client.get("/api/v1/vulns")
    assert resp.status_code == 401
