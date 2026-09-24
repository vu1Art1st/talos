"""API 集成测试：报告中心。

报告中心：编辑、章节不内嵌复测详情、由漏洞建报告与工单归属推断、测试目标
URL、相似度检查（含无快照历史数据）、重复导出拦截、漏洞状态自动化。

原 tests/test_api.py（4626 行单体）按领域拆分而来：用例源码逐字未改，
仅按领域重新归位；共享夹具见 tests/conftest.py，共享 helper 见 tests/api/_helpers.py。
"""
import pytest
from httpx import AsyncClient

from _helpers import _wait_job

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_report_edit_and_export(client: AsyncClient, auth: dict):
    # 自建数据（2026-09-22 拆分时整改）：原实现取「库中已有漏洞」，依赖其它模块先造数据，
    # 本模块单独运行 / 并行执行时 `GET /vulns` 可能为空。现自行建 2 条漏洞，
    # 断言口径不变（报告章节数、汇总表行数、详情标题数都按 len(vul_ids) 派生）。
    # 无需清理：测试 schema 按 pytest 进程隔离，并在 session 结束时整体 DROP。
    asset = (await client.post(
        "/api/v1/assets", headers=auth, json={"name": "报告编辑导出资产"},
    )).json()
    vul_ids = []
    for i, level in enumerate((20, 30), start=1):
        resp = await client.post(
            "/api/v1/vulns", headers=auth,
            json={"title": f"报告编辑导出漏洞{i}", "level": level, "asset_ids": [asset["id"]]},
        )
        assert resp.status_code == 200, resp.text
        vul_ids.append(resp.json()["id"])
    assert vul_ids

    resp = await client.post(
        "/api/v1/reports/from-vulns", headers=auth,
        json={"title": "季度渗透测试报告", "vul_ids": vul_ids},
    )
    assert resp.status_code == 200, resp.text
    report = resp.json()
    assert len(report["sections"]) == len(vul_ids)
    report_id = report["id"]

    # 错误 revision 保存应 409（乐观锁）
    save_body = {
        "title": "季度渗透测试报告 V2",
        "project_name": "商城安全测试",
        "revision": report["revision"] + 99,
        "sections": report["sections"],
    }
    resp = await client.put(f"/api/v1/reports/{report_id}", headers=auth, json=save_body)
    assert resp.status_code == 409

    # 正确 revision 保存成功：revision +1，导出 version 不受编辑影响
    save_body["revision"] = report["revision"]
    save_body["target_ip"] = "10.0.0.8"
    resp = await client.put(f"/api/v1/reports/{report_id}", headers=auth, json=save_body)
    assert resp.status_code == 200, resp.text
    saved = resp.json()
    assert saved["revision"] == report["revision"] + 1
    assert saved["version"] == report["version"]  # 保存不改导出版本号
    assert saved["title"] == "季度渗透测试报告 V2"
    assert saved["target_ip"] == "10.0.0.8"

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

    # 导出成功后导出版本 +1；测试周期在字段为空时自动预填（开始=最早提交日期，结束=当天）
    from app.core.timeutil import now as _tnow

    after = (await client.get(f"/api/v1/reports/{report_id}", headers=auth)).json()
    assert after["version"] == saved["version"] + 1
    assert after["test_start"]
    assert after["test_end"] == _tnow().date().isoformat()

    # 产物基于渗透测试报告模板：验证封面系统名称、测试目标 IP、汇总表与详情标题
    from io import BytesIO

    from docx import Document

    doc = Document(BytesIO(resp.content))
    texts = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
    assert "商城安全测试" in texts  # 封面第二行=系统名称(project_name)，报告标题作为文件名
    assert any(t == "风险问题详情" for t in texts)
    # 测试目标表：被测系统 IP
    target_tbl = doc.tables[4]
    assert target_tbl.rows[3].cells[1].text.strip() == "10.0.0.8"
    # 汇总表：表头 + 每个关联漏洞一行，且样例行已被替换
    summary_tbl = doc.tables[6]
    assert len(summary_tbl.rows) == 1 + len(vul_ids)
    assert "平行越权" not in summary_tbl.rows[1].cells[2].text
    # 详情段：每个章节一个 Heading 3，标题含修复状态后缀
    h3 = [p.text for p in doc.paragraphs if p.style.name == "Heading 3"]
    assert len(h3) == len(vul_ids)
    assert all(t.endswith("）") for t in h3)

async def test_report_from_vulns_infer_plan_id(client: AsyncClient, auth: dict):
    """from-vulns 未显式指定计划时：漏洞归属唯一计划则自动回写，多计划则不回写。"""
    # 计划一 + 归属该计划的两个漏洞
    resp = await client.post(
        "/api/v1/testing-plans", headers=auth,
        json={"system_name": "回写系统A", "test_type": "渗透测试"},
    )
    plan_a = resp.json()["id"]
    # 严格认领：需先认领计划才能批量建计划漏洞
    await client.post(f"/api/v1/testing-plans/{plan_a}/claim", headers=auth)
    resp = await client.post("/api/v1/assets", headers=auth, json={"name": "回写资产A"})
    asset_a = resp.json()["id"]
    resp = await client.post(
        "/api/v1/vulns/batch", headers=auth,
        json={"asset_ids": [asset_a], "vulns": [
            {"title": "回写漏洞A1", "level": 20, "testing_plan_id": plan_a},
            {"title": "回写漏洞A2", "level": 30, "testing_plan_id": plan_a},
        ]},
    )
    a1, a2 = [v["id"] for v in resp.json()]

    # 未传 testing_plan_id：唯一归属计划应被自动回写
    resp = await client.post(
        "/api/v1/reports/from-vulns", headers=auth,
        json={"title": "自动回写报告", "vul_ids": [a1, a2]},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["testing_plan_id"] == plan_a

    # 计划二 + 归属该计划的漏洞
    resp = await client.post(
        "/api/v1/testing-plans", headers=auth,
        json={"system_name": "回写系统B", "test_type": "渗透测试"},
    )
    plan_b = resp.json()["id"]
    await client.post(f"/api/v1/testing-plans/{plan_b}/claim", headers=auth)
    resp = await client.post("/api/v1/assets", headers=auth, json={"name": "回写资产B"})
    asset_b = resp.json()["id"]
    resp = await client.post(
        "/api/v1/vulns/batch", headers=auth,
        json={"asset_ids": [asset_b], "vulns": [
            {"title": "回写漏洞B1", "level": 20, "testing_plan_id": plan_b},
        ]},
    )
    b1 = resp.json()[0]["id"]

    # 跨两个计划的漏洞：归属不唯一，不回写
    resp = await client.post(
        "/api/v1/reports/from-vulns", headers=auth,
        json={"title": "多计划报告", "vul_ids": [a1, b1]},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["testing_plan_id"] is None

async def test_report_export_target_urls_from_plan(client: AsyncClient, auth: dict):
    """工单「被测系统URL」为报告测试目标表优先数据源：资产未录URL时导出仍能带出URL/域名。"""
    from io import BytesIO

    from docx import Document

    # 工单维护被测系统URL；关联资产未录URL
    resp = await client.post(
        "/api/v1/testing-plans", headers=auth,
        json={"system_name": "目标系统", "test_type": "渗透测试",
              "target_urls": ["https://target.example.com/app", "http://10.20.1.10:8080"]},
    )
    plan_id = resp.json()["id"]
    await client.post(f"/api/v1/testing-plans/{plan_id}/claim", headers=auth)
    resp = await client.post("/api/v1/assets", headers=auth, json={"name": "无URL资产"})
    asset_id = resp.json()["id"]
    resp = await client.post(
        "/api/v1/vulns/batch", headers=auth,
        json={"asset_ids": [asset_id], "vulns": [{"title": "目标漏洞", "level": 30}]},
    )
    vul_id = resp.json()[0]["id"]

    resp = await client.post(
        "/api/v1/reports/from-vulns", headers=auth,
        json={"title": "目标URL报告", "vul_ids": [vul_id], "testing_plan_id": plan_id},
    )
    report_id = resp.json()["id"]

    resp = await client.post(
        f"/api/v1/reports/{report_id}/export", headers=auth, json={"fmt": "docx"}
    )
    job_id = resp.json()["id"]
    job = await _wait_job(client, auth, report_id, job_id)
    assert job["status"] == "done", job

    resp = await client.get(f"/api/v1/reports/exports/{job_id}/download", headers=auth)
    doc = Document(BytesIO(resp.content))
    target_tbl = doc.tables[4]
    # URL格取工单 target_urls，域名格由URL推导（纯 IP hostname 不计入域名）
    assert target_tbl.rows[1].cells[1].text.strip() == "https://target.example.com/app\nhttp://10.20.1.10:8080"
    assert target_tbl.rows[2].cells[1].text.strip() == "target.example.com"

async def test_report_similarity_check(client: AsyncClient, auth: dict):
    """相似性检查：基础信息（标题+归属计划+漏洞集合）与所选漏洞最后编辑时间完全一致才判相似。"""
    resp = await client.post(
        "/api/v1/testing-plans", headers=auth,
        json={"system_name": "相似系统", "test_type": "渗透测试"},
    )
    plan_id = resp.json()["id"]
    # 录入漏洞需先认领计划（严格认领校验，管理员未认领也不放行）
    resp = await client.post(f"/api/v1/testing-plans/{plan_id}/claim", headers=auth)
    assert resp.status_code == 200, resp.text
    resp = await client.post("/api/v1/assets", headers=auth, json={"name": "相似资产"})
    asset_id = resp.json()["id"]
    resp = await client.post(
        "/api/v1/vulns/batch", headers=auth,
        json={"asset_ids": [asset_id], "vulns": [
            {"title": "相似漏洞A", "level": 20, "testing_plan_id": plan_id},
            {"title": "相似漏洞B", "level": 30, "testing_plan_id": plan_id},
        ]},
    )
    vul_a, vul_b = [v["id"] for v in resp.json()]

    # 生成报告后，同配置再次检查 → 高度相似
    resp = await client.post(
        "/api/v1/reports/from-vulns", headers=auth,
        json={"title": "相似性检查报告", "vul_ids": [vul_a, vul_b], "testing_plan_id": plan_id},
    )
    assert resp.status_code == 200, resp.text
    report_id = resp.json()["id"]

    async def check(**overrides):
        payload = {
            "title": "相似性检查报告",
            "vul_ids": [vul_a, vul_b],
            "testing_plan_id": plan_id,
            **overrides,
        }
        return (await client.post("/api/v1/reports/similarity-check", headers=auth, json=payload)).json()

    data = await check()
    assert data["similar"] is True
    assert [r["id"] for r in data["matched_reports"]] == [report_id]

    # 漏洞顺序无关（集合比较）
    assert (await check(vul_ids=[vul_b, vul_a]))["similar"] is True

    # 未显式传计划时，由漏洞归属唯一计划推导 → 同样命中
    payload = {"title": "相似性检查报告", "vul_ids": [vul_a, vul_b]}
    resp = await client.post("/api/v1/reports/similarity-check", headers=auth, json=payload)
    assert resp.json()["similar"] is True

    # 所选漏洞最后编辑时间变化（编辑漏洞）→ 不再相似
    resp = await client.put(f"/api/v1/vulns/{vul_a}", headers=auth, json={"title": "相似漏洞A-已修订"})
    assert resp.status_code == 200, resp.text
    assert (await check())["similar"] is False

    # 标题不同 / 漏洞集合不同 / 空集合 → 不相似
    assert (await check(title="完全不同标题"))["similar"] is False
    assert (await check(vul_ids=[vul_a]))["similar"] is False
    assert (await check(vul_ids=[]))["similar"] is False

async def test_report_similarity_check_legacy_no_snapshot(client: AsyncClient, auth: dict):
    """存量报告（无 vul_edit_snapshot）再次生成时：漏洞集合一致则回填快照并判相似。"""
    resp = await client.post(
        "/api/v1/testing-plans", headers=auth,
        json={"system_name": "存量系统", "test_type": "渗透测试"},
    )
    plan_id = resp.json()["id"]
    resp = await client.post(f"/api/v1/testing-plans/{plan_id}/claim", headers=auth)
    assert resp.status_code == 200, resp.text
    resp = await client.post("/api/v1/assets", headers=auth, json={"name": "存量资产"})
    asset_id = resp.json()["id"]
    resp = await client.post(
        "/api/v1/vulns/batch", headers=auth,
        json={"asset_ids": [asset_id], "vulns": [
            {"title": "存量漏洞A", "level": 20, "testing_plan_id": plan_id},
            {"title": "存量漏洞B", "level": 30, "testing_plan_id": plan_id},
        ]},
    )
    vul_a, vul_b = [v["id"] for v in resp.json()]
    resp = await client.post(
        "/api/v1/reports/from-vulns", headers=auth,
        json={"title": "存量相似报告", "vul_ids": [vul_a, vul_b], "testing_plan_id": plan_id},
    )
    assert resp.status_code == 200, resp.text
    report_id = resp.json()["id"]

    # 模拟存量数据：清空快照
    from sqlalchemy import select as sa_select

    from app.db import async_session_maker
    from app.models import Report

    async with async_session_maker() as session:
        report = (
            await session.execute(sa_select(Report).where(Report.id == report_id))
        ).scalar_one()
        report.vul_edit_snapshot = None
        await session.commit()

    async def check(**overrides):
        payload = {
            "title": "存量相似报告",
            "vul_ids": [vul_a, vul_b],
            "testing_plan_id": plan_id,
            **overrides,
        }
        resp = await client.post("/api/v1/reports/similarity-check", headers=auth, json=payload)
        return resp.json()

    # 无快照但基础信息与漏洞集合一致 → 判相似，且回填快照
    data = await check()
    assert data["similar"] is True
    assert [r["id"] for r in data["matched_reports"]] == [report_id]
    async with async_session_maker() as session:
        report = (
            await session.execute(sa_select(Report).where(Report.id == report_id))
        ).scalar_one()
        assert report.vul_edit_snapshot is not None

    # 回填后再次检查仍相似
    assert (await check())["similar"] is True

    # 漏洞集合不一致时不误匹配
    assert (await check(vul_ids=[vul_a]))["similar"] is False

    # 漏洞被编辑（快照已回填旧值）→ 不再相似
    resp = await client.put(f"/api/v1/vulns/{vul_a}", headers=auth, json={"title": "存量漏洞A-已修订"})
    assert resp.status_code == 200, resp.text
    assert (await check())["similar"] is False

async def test_report_export_duplicate_check(client: AsyncClient, auth: dict):
    """导出前重复判断：内容指纹与上次成功导出一致则 duplicate，编辑报告后不再重复。"""
    resp = await client.post("/api/v1/assets", headers=auth, json={"name": "重复导出资产"})
    asset_id = resp.json()["id"]
    resp = await client.post(
        "/api/v1/vulns/batch", headers=auth,
        json={"asset_ids": [asset_id], "vulns": [
            {"title": "重复导出漏洞A", "level": 20},
            {"title": "重复导出漏洞B", "level": 30},
        ]},
    )
    vul_ids = [v["id"] for v in resp.json()]
    resp = await client.post(
        "/api/v1/reports/from-vulns", headers=auth,
        json={"title": "重复导出检查报告", "vul_ids": vul_ids},
    )
    assert resp.status_code == 200, resp.text
    report_id = resp.json()["id"]

    async def check_export(fmt: str = "docx"):
        resp = await client.post(
            f"/api/v1/reports/{report_id}/export-check", headers=auth, json={"fmt": fmt},
        )
        assert resp.status_code == 200, resp.text
        return resp.json()

    # 尚无成功导出 → 不重复
    assert (await check_export())["duplicate"] is False

    # 导出 docx 并等待完成
    resp = await client.post(
        f"/api/v1/reports/{report_id}/export", headers=auth, json={"fmt": "docx"},
    )
    assert resp.status_code == 200, resp.text
    job = await _wait_job(client, auth, report_id, resp.json()["id"])
    assert job["status"] == "done", job

    # 内容未变 → 重复（附完整提示信息）；其他格式无历史 → 不重复
    data = await check_export()
    assert data["duplicate"] is True
    assert data["fmt"] == "docx"
    assert data["report_title"] == "重复导出检查报告"
    assert data["last_status"] == "done"
    assert data["last_time"] is not None
    assert data["last_version"] == 2  # 初始 v1 + 导出成功后版本 +1
    assert data["last_file_name"].endswith(".docx")
    assert (await check_export("pdf"))["duplicate"] is False

    # 编辑报告（revision/update_time 变化）→ 不再重复
    detail = (await client.get(f"/api/v1/reports/{report_id}", headers=auth)).json()
    save_body = {
        "title": "重复导出检查报告",
        "revision": detail["revision"],
        "sections": detail["sections"],
    }
    resp = await client.put(f"/api/v1/reports/{report_id}", headers=auth, json=save_body)
    assert resp.status_code == 200, resp.text
    assert (await check_export())["duplicate"] is False

async def test_report_vuln_state_automation(client: AsyncClient, auth: dict):
    """报告联动状态机：生成报告→修复中，发起复测→复测中，全部已修复/已忽略→报告已完成。"""
    resp = await client.post("/api/v1/assets", headers=auth, json={"name": "联动测试系统"})
    asset_id = resp.json()["id"]
    resp = await client.post(
        "/api/v1/vulns/batch", headers=auth,
        json={
            "asset_ids": [asset_id],
            "vulns": [{"title": "联动漏洞A", "level": 20}, {"title": "联动漏洞B", "level": 30}],
        },
    )
    vul_a, vul_b = [v["id"] for v in resp.json()]

    # 生成报告后关联漏洞自动进入修复中
    resp = await client.post(
        "/api/v1/reports/from-vulns", headers=auth,
        json={"title": "联动测试报告", "vul_ids": [vul_a, vul_b]},
    )
    assert resp.status_code == 200, resp.text
    report_id = resp.json()["id"]
    for vid in (vul_a, vul_b):
        vul = (await client.get(f"/api/v1/vulns/{vid}", headers=auth)).json()
        assert vul["status"] == 50
        assert vul["notice_time"] is not None

    # 点击复测：关联漏洞自动进入复测中
    resp = await client.post(f"/api/v1/reports/{report_id}/retest", headers=auth)
    assert resp.status_code == 200, resp.text
    for vid in (vul_a, vul_b):
        vul = (await client.get(f"/api/v1/vulns/{vid}", headers=auth)).json()
        assert vul["status"] == 55

    # 复测面板数据源：报告关联漏洞状态列表
    resp = await client.get(f"/api/v1/reports/{report_id}/vuln-states", headers=auth)
    assert resp.status_code == 200, resp.text
    states = resp.json()
    assert {s["vul_id"] for s in states} == {vul_a, vul_b}
    assert all(s["status"] == 55 for s in states)

    # 复测中可选：已修复/复测未通过(回修复中)/已忽略/暂不处理
    resp = await client.get(f"/api/v1/vulns/{vul_a}/transitions", headers=auth)
    assert {t["status"] for t in resp.json()} == {20, 35, 50, 60}

    # A 已修复（携带复测详情）：报告尚未全部处理完，不应自动完成
    resp = await client.post(
        f"/api/v1/vulns/{vul_a}/transition", headers=auth,
        json={
            "status": 60,
            "retest_html": "<p>复测通过，漏洞已修复</p>",
            "retest_json": {"type": "doc", "content": []},
        },
    )
    assert resp.status_code == 200
    assert resp.json()["retest_html"] == "<p>复测通过，漏洞已修复</p>"
    vul = (await client.get(f"/api/v1/vulns/{vul_a}", headers=auth)).json()
    assert vul["retest_html"] == "<p>复测通过，漏洞已修复</p>"
    assert vul["retest_json"] == {"type": "doc", "content": []}

    # B 已忽略：全部为已修复/已忽略，计划复测完成
    resp = await client.post(
        f"/api/v1/vulns/{vul_b}/transition", headers=auth, json={"status": 20},
    )
    assert resp.status_code == 200

    # 无关联漏洞的报告不能发起复测
    resp = await client.post("/api/v1/reports", headers=auth, json={"title": "空报告", "sections": []})
    empty_id = resp.json()["id"]
    resp = await client.post(f"/api/v1/reports/{empty_id}/retest", headers=auth)
    assert resp.status_code == 400

async def test_report_section_excludes_retest(client: AsyncClient, auth: dict):
    """含复测内容的漏洞生成报告：章节快照不再内嵌复测详情。

    回归：内嵌快照会与复测详情面板重复展示，且快照不随复测更新——导出时还会因
    「正文已含复测详情」跳过追加最新内容。复测详情以漏洞字段为唯一权威来源，
    由导出流程统一追加一次。
    """
    resp = await client.post(
        "/api/v1/vulns", headers=auth, json={"title": "报告复测漏洞", "level": 20},
    )
    vul_id = resp.json()["id"]
    resp = await client.post(
        f"/api/v1/vulns/{vul_id}/retests", headers=auth,
        json={"content_html": "<p>复测发现仍可利用</p>", "content_json": None},
    )
    assert resp.status_code == 200, resp.text

    resp = await client.post(
        "/api/v1/reports/from-vulns", headers=auth,
        json={"title": "复测内容报告", "vul_ids": [vul_id]},
    )
    assert resp.status_code == 200, resp.text
    section = resp.json()["sections"][0]
    assert "复测详情" not in section["content_html"]

    detail = (await client.get(f"/api/v1/vulns/{vul_id}", headers=auth)).json()
    assert "复测发现仍可利用" in detail["retest_html"]
