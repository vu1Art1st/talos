"""API 集成测试：认证 → 业务 CRUD → 状态机 → Word 导入 → 报告与导出全链路。"""
import asyncio
import json
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


async def test_asset_and_vuln_lifecycle(client: AsyncClient, auth: dict):
    # 建资产（系统级：负责人 / URL 标签 / 端口服务对 / 中间件与数据库多条目）
    resp = await client.post(
        "/api/v1/assets", headers=auth,
        json={
            "name": "测试商城",
            "sub_system": "订单中心",
            "department": "电商事业部",
            "public_urls": [{"url": "https://shop.example.com", "tag": 10}],
            "internal_urls": ["http://10.0.0.8:8080"],
            "port_services": [
                {"port": "80", "service": "Web服务"},
                {"port": "443", "service": "HTTPS"},
            ],
            "middlewares": [{"name": "Nginx", "version": "1.24"}],
            "databases": [{"name": "MySQL", "version": "8.0"}],
            "owners": [{"name": "张三", "phone": "13800000000", "email": "zhangsan@example.com"}],
        },
    )
    assert resp.status_code == 200, resp.text
    asset = resp.json()
    asset_id = asset["id"]
    assert asset["owners"][0]["name"] == "张三"
    assert asset["public_urls"][0]["tag"] == 10
    assert asset["port_services"][1] == {"port": "443", "service": "HTTPS"}
    assert asset["middlewares"][0]["version"] == "1.24"
    assert asset["databases"][0] == {"name": "MySQL", "version": "8.0"}

    # 系统命名必填
    resp = await client.post("/api/v1/assets", headers=auth, json={"name": ""})
    assert resp.status_code == 422

    # 建漏洞（未修复 10），多对多关联资产
    resp = await client.post(
        "/api/v1/vulns", headers=auth,
        json={
            "title": "订单接口越权", "level": 20, "vul_type": 30,
            "affected_url": "https://shop.example.com/api/order",
            "description_html": "<p>横向越权读取他人订单</p>",
            "asset_ids": [asset_id],
        },
    )
    assert resp.status_code == 200, resp.text
    vul = resp.json()
    assert vul["status"] == 10
    assert vul["asset_ids"] == [asset_id]
    assert vul["assets"][0]["name"] == "测试商城"
    vul_id = vul["id"]

    # 按资产筛选漏洞
    resp = await client.get("/api/v1/vulns", headers=auth, params={"asset_id": asset_id})
    assert vul_id in [v["id"] for v in resp.json()["items"]]

    # 已关联漏洞的资产不能删除
    resp = await client.delete(f"/api/v1/assets/{asset_id}", headers=auth)
    assert resp.status_code == 400

    # 未修复可流转到：已忽略/暂不处理/修复中/复测中（复测中为修复状态冗余兜底路径）
    resp = await client.get(f"/api/v1/vulns/{vul_id}/transitions", headers=auth)
    assert {t["status"] for t in resp.json()} == {20, 35, 50, 55}

    # 10 -> 50 进入修复中，打 notice_time
    resp = await client.post(
        f"/api/v1/vulns/{vul_id}/transition", headers=auth,
        json={"status": 50, "comment": "已出报告"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == 50
    assert resp.json()["notice_time"] is not None

    # 非法流转 50 -> 60 应被拒绝（必须经过复测）
    resp = await client.post(
        f"/api/v1/vulns/{vul_id}/transition", headers=auth,
        json={"status": 60},
    )
    assert resp.status_code == 400

    # 50 -> 55 复测中 -> 60 已修复（终态，须携带复测内容）
    resp = await client.post(
        f"/api/v1/vulns/{vul_id}/transition", headers=auth, json={"status": 55},
    )
    assert resp.status_code == 200
    assert resp.json()["is_retest"] is True
    resp = await client.post(
        f"/api/v1/vulns/{vul_id}/transition", headers=auth,
        json={"status": 60, "comment": "复测通过", "retest_html": "<p>复测通过</p>"},
    )
    assert resp.status_code == 200
    assert resp.json()["fix_time"] is not None
    # 已修复为可回退状态：可重新打开为未修复(10)或直接重新复测(55)
    resp = await client.get(f"/api/v1/vulns/{vul_id}/transitions", headers=auth)
    assert {t["status"] for t in resp.json()} == {10, 55}

    # 日志包含创建与状态流转
    resp = await client.get(f"/api/v1/vulns/{vul_id}/logs", headers=auth)
    actions = [log["action"] for log in resp.json()]
    assert "创建漏洞" in actions
    assert len(actions) >= 2


async def test_vuln_batch_create(client: AsyncClient, auth: dict):
    resp = await client.post(
        "/api/v1/assets", headers=auth, json={"name": "批量目标系统"},
    )
    asset_id = resp.json()["id"]

    resp = await client.post(
        "/api/v1/vulns/batch", headers=auth,
        json={
            "asset_ids": [asset_id],
            "vulns": [
                {"title": "批量漏洞A", "level": 20, "vul_type": 10},
                {"title": "批量漏洞B", "level": 30, "vul_type": 15},
                {"title": "批量漏洞C", "level": 40, "vul_type": 55},
            ],
        },
    )
    assert resp.status_code == 200, resp.text
    vulns = resp.json()
    assert len(vulns) == 3
    assert all(v["asset_ids"] == [asset_id] for v in vulns)

    # 无效资产ID被拒绝
    resp = await client.post(
        "/api/v1/vulns/batch", headers=auth,
        json={"asset_ids": [999999], "vulns": [{"title": "无效资产"}]},
    )
    assert resp.status_code == 400


async def test_asset_excel_import_export(client: AsyncClient, auth: dict):
    from openpyxl import Workbook, load_workbook

    # 构造导入文件：1 行合法 + 1 行缺系统命名
    wb = Workbook()
    ws = wb.active
    # 表头与模板一致（assets.py EXCEL_HEADERS，含「系统类型」列）
    ws.append(["系统命名*", "子系统名称", "部门", "系统类型", "公网URL", "内网URL",
               "开放端口与服务", "中间件", "数据库", "系统负责人", "状态", "备注"])
    ws.append(["Excel导入系统", "支付子系统", "金融部", "自有系统",
               "https://pay.example.com|互联网;https://oa.example.com|办公网",
               "http://192.168.1.10", "443:支付服务;8443:管理后台", "Tomcat/9.0", "Oracle/19c",
               "李四/13900000000/lisi@example.com;王五//wangwu@example.com",
               "线上", "备注内容"])
    ws.append(["", "无名子系统", "", "", "", "", "", "", "", "", "", ""])
    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)

    resp = await client.post(
        "/api/v1/assets/import", headers=auth,
        files={"file": ("assets.xlsx", buf,
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert resp.status_code == 200, resp.text
    result = resp.json()
    assert result["total"] == 2
    assert result["success"] == 1
    assert result["failed"] == 1
    assert "系统命名为必填项" in result["errors"][0]

    # 非 xlsx 拒绝
    resp = await client.post(
        "/api/v1/assets/import", headers=auth,
        files={"file": ("bad.txt", b"hello", "text/plain")},
    )
    assert resp.status_code == 400

    # 导入结果校验（多值字段解析）
    resp = await client.get("/api/v1/assets", headers=auth, params={"search": "Excel导入系统"})
    items = resp.json()["items"]
    assert len(items) == 1
    imported = items[0]
    assert imported["public_urls"] == [
        {"url": "https://pay.example.com", "tag": 10},
        {"url": "https://oa.example.com", "tag": 20},
    ]
    assert imported["port_services"] == [
        {"port": "443", "service": "支付服务"},
        {"port": "8443", "service": "管理后台"},
    ]
    assert imported["middlewares"] == [{"name": "Tomcat", "version": "9.0"}]
    assert imported["databases"] == [{"name": "Oracle", "version": "19c"}]
    assert len(imported["owners"]) == 2
    assert imported["owners"][1] == {"name": "王五", "phone": "", "email": "wangwu@example.com"}

    # 导出并回读
    resp = await client.get("/api/v1/assets/export", headers=auth, params={"search": "Excel导入系统"})
    assert resp.status_code == 200
    wb = load_workbook(BytesIO(resp.content))
    rows = list(wb.active.iter_rows(values_only=True))
    assert len(rows) == 2  # 表头 + 1 行数据
    assert rows[1][0] == "Excel导入系统"
    assert rows[1][3] == "自有系统"  # 系统类型列
    assert "互联网" in rows[1][4]  # 公网URL列
    assert rows[1][6] == "443:支付服务;8443:管理后台"
    assert rows[1][7] == "Tomcat/9.0"

    # 模板下载
    resp = await client.get("/api/v1/assets/import/template", headers=auth)
    assert resp.status_code == 200
    assert resp.content[:2] == b"PK"


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


def _build_report_docx(system_name: str, target_url: str, target_ip: str, sections: list[tuple[str, str, str, bool]]):
    """构造平台报告格式 docx：测试目标表 + 风险问题汇总表 + 风险问题详情章节。

    sections: [(标题, 等级文本, 类型文本, 是否已修复)]
    """
    from docx import Document

    doc = Document()
    # 测试目标表
    t = doc.add_table(rows=3, cols=2)
    t.rows[0].cells[0].text, t.rows[0].cells[1].text = "业务系统名称", system_name
    t.rows[1].cells[0].text, t.rows[1].cells[1].text = "被测系统URL", target_url
    t.rows[2].cells[0].text, t.rows[2].cells[1].text = "被测系统IP", target_ip
    # 风险问题汇总表
    doc.add_heading("风险问题汇总", level=1)
    s = doc.add_table(rows=1 + len(sections), cols=4)
    for i, h in enumerate(("问题等级", "风险类型", "风险问题", "修复状态")):
        s.rows[0].cells[i].text = h
    for ri, (title, level_text, type_text, fixed) in enumerate(sections, start=1):
        s.rows[ri].cells[0].text = level_text
        s.rows[ri].cells[1].text = type_text
        s.rows[ri].cells[2].text = title
        s.rows[ri].cells[3].text = "已修复" if fixed else "未修复"
    # 风险问题详情
    doc.add_heading("风险问题详情", level=1)
    for title, _lvl, _typ, fixed in sections:
        suffix = "（已修复）" if fixed else "（未修复）"
        doc.add_heading(f"{title}{suffix}", level=3)
        doc.add_paragraph("漏洞链接")
        doc.add_paragraph(target_url)
        doc.add_paragraph("漏洞描述")
        doc.add_paragraph("此处为漏洞描述内容。")
        doc.add_paragraph("漏洞证明")
        doc.add_paragraph("此处为漏洞证明内容。")
        doc.add_paragraph("修复建议")
        doc.add_paragraph("此处为修复建议内容。")
        doc.add_paragraph("20260728漏洞复测")
        doc.add_paragraph("复测详情：已按建议整改。")
    return doc


async def _import_report(client: AsyncClient, auth: dict, filename: str, doc):
    buf = BytesIO()
    doc.save(buf)
    buf.seek(0)
    resp = await client.post(
        "/api/v1/imports", headers=auth,
        files={"file": (filename, buf,
                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
    )
    assert resp.status_code == 200, resp.text
    batch_id = resp.json()["id"]
    detail = await _wait_batch(client, auth, batch_id)
    assert detail["batch"]["status"] == "parsed", detail
    assert detail["batch"]["doc_kind"] == "report", detail
    rec_ids = [r["id"] for r in detail["records"]]
    resp = await client.post(
        f"/api/v1/imports/{batch_id}/confirm", headers=auth,
        json={"record_ids": rec_ids},
    )
    assert resp.status_code == 200, resp.text
    return detail["records"], resp.json()


async def _find_vuln(client: AsyncClient, auth: dict, keyword: str) -> dict:
    resp = await client.get("/api/v1/vulns", headers=auth, params={"search": keyword})
    items = resp.json()["items"]
    assert items, f"未找到漏洞：{keyword}"
    return items[0]


async def test_report_import_partial_fixed_flow(client: AsyncClient, auth: dict):
    """复测报告含未修复漏洞：计划应为复测中(50)、未修复漏洞置复测中(55)、自动建资产与报告。"""
    system_name = "综合办公系统ZZ"
    target_url = "http://10.9.9.9/officezz"
    doc = _build_report_docx(
        system_name, target_url, "10.9.9.9",
        sections=[
            ("平行越权访问漏洞ZZ", "高危", "逻辑漏洞", True),
            ("敏感信息泄露漏洞ZZ", "中危", "信息泄露", False),
        ],
    )
    _records, result = await _import_report(
        client, auth, "20260728综合办公系统ZZ渗透测试复测报告.docx", doc,
    )
    assert result["created"] == 2

    # 计划：复测中(50)，不是复测完成(60)
    resp = await client.get("/api/v1/testing-plans", headers=auth, params={"search": system_name})
    plans = resp.json()["items"]
    assert len(plans) == 1, plans
    assert plans[0]["status"] == 50

    # 已修复漏洞 → 60；未修复漏洞 → 55（复测中，可在报告编辑页填写复测结论）
    fixed_vuln = await _find_vuln(client, auth, "平行越权访问漏洞ZZ")
    assert fixed_vuln["status"] == 60
    unfixed_vuln = await _find_vuln(client, auth, "敏感信息泄露漏洞ZZ")
    assert unfixed_vuln["status"] == 55
    assert any(a["name"] == system_name for a in unfixed_vuln["assets"])

    # 自动创建资产：系统名匹配，被测 URL 入内网地址
    resp = await client.get("/api/v1/assets", headers=auth, params={"search": system_name})
    assets = [a for a in resp.json()["items"] if a["name"] == system_name]
    assert assets, "未自动创建资产"
    assert target_url in (assets[0]["internal_urls"] or [])

    # 自动创建报告：显示在报告中心，草稿态，章节数与漏洞数一致
    resp = await client.get("/api/v1/reports", headers=auth, params={"search": system_name})
    reports = [r for r in resp.json()["items"] if r["project_name"] == system_name]
    assert reports, "未自动创建报告"
    report = reports[0]
    assert report["status"] == "draft"
    assert report["testing_plan_id"] == plans[0]["id"]
    detail = await client.get(f"/api/v1/reports/{report['id']}", headers=auth)
    assert len(detail.json()["sections"]) == 2


async def test_report_import_all_fixed_flow(client: AsyncClient, auth: dict):
    """复测报告全部修复：计划复测完成(60)、报告保持草稿(draft，定稿由导出 Word 驱动)。"""
    system_name = "门户系统ZZ"
    doc = _build_report_docx(
        system_name, "http://10.8.8.8/portalzz", "10.8.8.8",
        sections=[("命令执行漏洞ZZ", "高危", "命令执行漏洞", True)],
    )
    _records, result = await _import_report(
        client, auth, "20260728门户系统ZZ渗透测试复测报告.docx", doc,
    )
    assert result["created"] == 1

    resp = await client.get("/api/v1/testing-plans", headers=auth, params={"search": system_name})
    plans = resp.json()["items"]
    assert len(plans) == 1 and plans[0]["status"] == 60

    resp = await client.get("/api/v1/reports", headers=auth, params={"search": system_name})
    reports = [r for r in resp.json()["items"] if r["project_name"] == system_name]
    assert reports and reports[0]["status"] == "draft"


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
    report = (await client.get(f"/api/v1/reports/{report_id}", headers=auth)).json()
    assert report["status"] == "draft"

    # B 已忽略：全部为已修复/已忽略，计划复测完成，报告保持草稿（需求6：报告状态由导出定稿驱动）
    resp = await client.post(
        f"/api/v1/vulns/{vul_b}/transition", headers=auth, json={"status": 20},
    )
    assert resp.status_code == 200
    report = (await client.get(f"/api/v1/reports/{report_id}", headers=auth)).json()
    assert report["status"] == "draft"

    # 无关联漏洞的报告不能发起复测
    resp = await client.post("/api/v1/reports", headers=auth, json={"title": "空报告", "sections": []})
    empty_id = resp.json()["id"]
    resp = await client.post(f"/api/v1/reports/{empty_id}/retest", headers=auth)
    assert resp.status_code == 400


async def test_retest_keeps_fixed_vuln_status(client: AsyncClient, auth: dict):
    """发起复测仅对未修复漏洞生效：已修复(60)漏洞保持原状态，不重新进入复测中。"""
    resp = await client.post("/api/v1/assets", headers=auth, json={"name": "复测筛选测试系统"})
    asset_id = resp.json()["id"]
    resp = await client.post(
        "/api/v1/vulns/batch", headers=auth,
        json={
            "asset_ids": [asset_id],
            "vulns": [{"title": "筛选漏洞A", "level": 20}, {"title": "筛选漏洞B", "level": 30}],
        },
    )
    vul_a, vul_b = [v["id"] for v in resp.json()]

    # 生成报告 → 修复中(50)；首次发起复测 → 复测中(55)
    resp = await client.post(
        "/api/v1/reports/from-vulns", headers=auth,
        json={"title": "复测筛选报告", "vul_ids": [vul_a, vul_b]},
    )
    assert resp.status_code == 200, resp.text
    report_id = resp.json()["id"]
    resp = await client.post(f"/api/v1/reports/{report_id}/retest", headers=auth)
    assert resp.status_code == 200, resp.text

    # A 已修复（携带复测详情）
    resp = await client.post(
        f"/api/v1/vulns/{vul_a}/transition", headers=auth,
        json={"status": 60, "retest_html": "<p>复测通过</p>"},
    )
    assert resp.status_code == 200
    assert (await client.get(f"/api/v1/vulns/{vul_a}", headers=auth)).json()["status"] == 60

    # 再次发起复测：已修复 A 保持 60，未修复 B 保持 55，均不重复进入复测中
    resp = await client.post(f"/api/v1/reports/{report_id}/retest", headers=auth)
    assert resp.status_code == 200, resp.text
    assert (await client.get(f"/api/v1/vulns/{vul_a}", headers=auth)).json()["status"] == 60
    assert (await client.get(f"/api/v1/vulns/{vul_b}", headers=auth)).json()["status"] == 55

    # 全部漏洞已修复后再次发起复测：均不再进入复测中，保持已修复
    resp = await client.post(
        f"/api/v1/vulns/{vul_b}/transition", headers=auth,
        json={"status": 60, "retest_html": "<p>复测通过</p>"},
    )
    assert resp.status_code == 200
    resp = await client.post(f"/api/v1/reports/{report_id}/retest", headers=auth)
    assert resp.status_code == 200, resp.text
    assert (await client.get(f"/api/v1/vulns/{vul_a}", headers=auth)).json()["status"] == 60
    assert (await client.get(f"/api/v1/vulns/{vul_b}", headers=auth)).json()["status"] == 60


async def test_retest_blocked_without_update(client: AsyncClient, auth: dict):
    """复测报告生成防重：漏洞状态/内容未更新时再次发起复测被阻止（不新增报告、不增加轮次）；
    状态有更新后允许再次发起复测，同日标题重复自动追加 -1 后缀。"""
    resp = await client.post(
        "/api/v1/testing-plans", headers=auth,
        json={"system_name": "复测防重系统", "test_type": "渗透测试"},
    )
    assert resp.status_code == 200, resp.text
    plan_id = resp.json()["id"]
    resp = await client.post(f"/api/v1/testing-plans/{plan_id}/claim", headers=auth)
    assert resp.status_code == 200, resp.text
    resp = await client.post("/api/v1/assets", headers=auth, json={"name": "复测防重资产"})
    asset_id = resp.json()["id"]
    resp = await client.post(
        "/api/v1/vulns/batch", headers=auth,
        json={"asset_ids": [asset_id], "vulns": [
            {"title": "防重漏洞A", "level": 20, "testing_plan_id": plan_id},
            {"title": "防重漏洞B", "level": 30, "testing_plan_id": plan_id},
        ]},
    )
    assert resp.status_code == 200, resp.text
    vul_a, vul_b = [v["id"] for v in resp.json()]

    # 生成初测报告 → 漏洞进入修复中(50)
    resp = await client.post(
        "/api/v1/reports/from-vulns", headers=auth,
        json={"title": "防重系统渗透测试报告", "vul_ids": [vul_a, vul_b], "testing_plan_id": plan_id},
    )
    assert resp.status_code == 200, resp.text
    src_report = resp.json()["id"]

    # 第一次发起复测 → 生成复测报告 R1，漏洞进入复测中(55)
    resp = await client.post(f"/api/v1/reports/{src_report}/retest", headers=auth)
    assert resp.status_code == 200, resp.text
    r1_id = resp.json()["id"]
    assert (await client.get(f"/api/v1/vulns/{vul_a}", headers=auth)).json()["status"] == 55

    # 状态/内容未变化再次发起复测 → 阻止并提示，不新增报告、不增加轮次
    resp = await client.post(f"/api/v1/reports/{src_report}/retest", headers=auth)
    assert resp.status_code == 400, resp.text
    assert "复测结果未更新" in resp.json()["detail"]
    plan = (await client.get(f"/api/v1/testing-plans/{plan_id}", headers=auth)).json()
    assert len(plan["reports"]) == 2
    assert plan["retest_round_count"] == 1

    # 处理复测：A 已修复（携带复测内容）→ 状态有更新，允许再次发起复测
    resp = await client.post(
        f"/api/v1/vulns/{vul_a}/transition", headers=auth,
        json={"status": 60, "retest_html": "<p>复测通过</p>"},
    )
    assert resp.status_code == 200
    resp = await client.post(f"/api/v1/reports/{src_report}/retest", headers=auth)
    assert resp.status_code == 200, resp.text
    r2_id = resp.json()["id"]
    assert r2_id != r1_id
    # 同日标题重复 → 自动追加 -1 后缀
    assert resp.json()["title"].endswith("-1")

    # 最终：1 初测报告 + 2 复测报告；复测轮数 2（被阻止的一次未计入）
    plan = (await client.get(f"/api/v1/testing-plans/{plan_id}", headers=auth)).json()
    assert len(plan["reports"]) == 3
    assert plan["retest_round_count"] == 2


async def test_import_confirm_into_report(client: AsyncClient, auth: dict):
    """Word 导入确认时关联报告：自动追加章节、漏洞进入修复中。"""
    resp = await client.post(
        "/api/v1/reports", headers=auth, json={"title": "导入关联报告", "sections": []},
    )
    report = resp.json()
    report_id = report["id"]

    resp = await client.get("/api/v1/imports/template", headers=auth)
    resp = await client.post(
        "/api/v1/imports", headers=auth,
        files={"file": ("关联报告样例.docx", BytesIO(resp.content),
                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
    )
    batch_id = resp.json()["id"]
    detail = await _wait_batch(client, auth, batch_id)
    assert detail["batch"]["status"] == "parsed", detail
    rec = detail["records"][0]

    # 不存在的报告被拒绝
    resp = await client.post(
        f"/api/v1/imports/{batch_id}/confirm", headers=auth,
        json={"record_ids": [rec["id"]], "report_id": 999999},
    )
    assert resp.status_code == 400

    resp = await client.post(
        f"/api/v1/imports/{batch_id}/confirm", headers=auth,
        json={"record_ids": [rec["id"]], "report_id": report_id},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["created"] == 1

    # 报告新增关联章节且编辑锁 revision +1（导出版本号 version 不受编辑影响）
    saved = (await client.get(f"/api/v1/reports/{report_id}", headers=auth)).json()
    assert len(saved["sections"]) == 1
    assert saved["sections"][0]["vul_id"] is not None
    assert saved["revision"] == report["revision"] + 1

    # 入库漏洞自动进入修复中
    vul = (await client.get(f"/api/v1/vulns/{saved['sections'][0]['vul_id']}", headers=auth)).json()
    assert vul["status"] == 50


async def test_special_modules_crud(client: AsyncClient, auth: dict):
    """三个专项模块：远程检测 / 测试计划 / 春耕行动 CRUD。"""
    # ---- 远程检测 ----
    resp = await client.post(
        "/api/v1/remote-testings", headers=auth,
        json={"title": "远程检测A", "system_name": "门户系统", "test_time": "2026-01-10",
              "department": "信息部", "appeal_success": False, "appeal_report_id": None},
    )
    assert resp.status_code == 200, resp.text
    rt_id = resp.json()["id"]

    # 不存在的申诉报告被拒绝
    resp = await client.post(
        "/api/v1/remote-testings", headers=auth,
        json={"title": "坏申诉", "appeal_report_id": 999999},
    )
    assert resp.status_code == 400

    resp = await client.put(
        f"/api/v1/remote-testings/{rt_id}", headers=auth,
        json={"title": "远程检测A-改", "system_name": "门户系统", "test_time": "2026-01-10",
              "department": "信息部", "appeal_success": True, "appeal_report_id": None},
    )
    assert resp.status_code == 200
    assert resp.json()["appeal_success"] is True

    resp = await client.get("/api/v1/remote-testings", headers=auth, params={"search": "门户"})
    assert rt_id in [r["id"] for r in resp.json()["items"]]

    # ---- 测试计划 ----
    resp = await client.post(
        "/api/v1/testing-plans", headers=auth,
        json={"system_name": "计划系统", "test_type": "渗透测试", "department": "研发部",
              "receive_time": "2026-01-01", "first_test_done_time": "2026-01-05",
              "status": 20, "stat_critical": 1, "stat_high": 2, "stat_medium": 3,
              "stat_low": 4, "brief": "共10个漏洞", "detail": "测试人员：张三"},
    )
    assert resp.status_code == 200, resp.text
    plan = resp.json()
    assert plan["stat_high"] == 2

    # status 筛选
    resp = await client.get("/api/v1/testing-plans", headers=auth, params={"status": 20})
    assert plan["id"] in [p["id"] for p in resp.json()["items"]]
    resp = await client.get("/api/v1/testing-plans", headers=auth, params={"status": 50})
    assert plan["id"] not in [p["id"] for p in resp.json()["items"]]

    # meta 提供六档状态字典
    meta = (await client.get("/api/v1/meta", headers=auth)).json()
    assert meta["testing_plan_status"]["10"] == "未测试"
    assert meta["testing_plan_status"]["60"] == "复测完成"

    # ---- 春耕行动 ----
    resp = await client.post(
        "/api/v1/vulns", headers=auth, json={"title": "春耕漏洞", "level": 20},
    )
    vul_id = resp.json()["id"]

    # 不存在的漏洞被拒绝
    resp = await client.post(
        "/api/v1/spring-actions", headers=auth,
        json={"report_no": "RPT-BAD", "vul_ids": [999999]},
    )
    assert resp.status_code == 400

    resp = await client.post(
        "/api/v1/spring-actions", headers=auth,
        json={"report_no": "RPT-2026-001", "system_name": "春耕系统",
              "appeal_success": True, "score_deduction": 2.5,
              "doc_no": "公文〔2026〕1号", "vul_ids": [vul_id]},
    )
    assert resp.status_code == 200, resp.text
    sa = resp.json()
    assert sa["vul_ids"] == [vul_id]
    assert sa["vuls"][0]["title"] == "春耕漏洞"
    assert sa["score_deduction"] == 2.5

    # 更新：清空漏洞关联
    resp = await client.put(
        f"/api/v1/spring-actions/{sa['id']}", headers=auth,
        json={"report_no": "RPT-2026-001", "system_name": "春耕系统",
              "appeal_success": False, "score_deduction": 0,
              "doc_no": "", "vul_ids": []},
    )
    assert resp.status_code == 200
    assert resp.json()["vuls"] == []

    # 列表返回漏洞摘要
    resp = await client.get("/api/v1/spring-actions", headers=auth, params={"search": "RPT-2026"})
    assert len(resp.json()["items"]) == 1

    # ---- 删除 ----
    for path in (f"/api/v1/remote-testings/{rt_id}",
                 f"/api/v1/testing-plans/{plan['id']}",
                 f"/api/v1/spring-actions/{sa['id']}"):
        resp = await client.delete(path, headers=auth)
        assert resp.status_code == 200


async def _get_plan(client: AsyncClient, auth: dict, plan_id: int) -> dict:
    resp = await client.get("/api/v1/testing-plans", headers=auth, params={"size": 100})
    return next(p for p in resp.json()["items"] if p["id"] == plan_id)


async def _list_plan_names(client: AsyncClient, auth: dict, params: dict) -> set[str]:
    resp = await client.get("/api/v1/testing-plans", headers=auth, params={"size": 100, **params})
    assert resp.status_code == 200, resp.text
    return {p["system_name"] for p in resp.json()["items"]}


async def test_testing_plan_filters(client: AsyncClient, auth: dict):
    """聚合筛选：多字段规则 + and/or 连接 + not 取反 + 派生/关联字段 + 非法入参。

    系统名/部门均使用唯一前缀，且断言限定在专属部门范围内，避免共享会话数据库
    中其他测试残留计划干扰精确集合比较。
    """
    DEPT = "筛选专用部门"
    A = "筛选专用系统-渗透A"
    B = "筛选专用系统-审计B"
    C = "筛选专用系统-渗透C"
    bodies = [
        {"system_name": A, "test_type": "渗透测试", "department": DEPT,
         "receive_time": "2026-01-01", "status": 10, "est_mandays": 3},
        {"system_name": B, "test_type": "代码审计", "department": "筛选专用部门B",
         "receive_time": "2026-02-01", "status": 20, "est_mandays": 5},
        {"system_name": C, "test_type": "渗透测试", "department": DEPT,
         "receive_time": "2026-03-01", "status": 60, "est_mandays": 2},
    ]
    plans = []
    for body in bodies:
        resp = await client.post("/api/v1/testing-plans", headers=auth, json=body)
        assert resp.status_code == 200, resp.text
        plans.append(resp.json())
    try:
        def rule(field, op, value=None, *, not_=False, connector="and"):
            return {"field": field, "op": op, "value": value, "not": not_, "connector": connector}

        def q(*rules):
            return {"filters": json.dumps({"rules": list(rules)})}

        dept = rule("department", "eq", DEPT)

        # 单条件：部门等于
        assert await _list_plan_names(client, auth, q(dept)) == {A, C}
        # 文本包含
        assert await _list_plan_names(client, auth, q(rule("system_name", "contains", "筛选专用系统-渗透"))) == {A, C}
        # AND 组合：部门=专属部门 且 状态=10
        assert await _list_plan_names(client, auth, q(dept, rule("status", "eq", 10))) == {A}
        # NOT 取反：部门=专属部门 且 状态≠10
        assert await _list_plan_names(client, auth, q(dept, rule("status", "ne", 10))) == {C}
        # OR 组合：规则间按顺序左结合（AND 优先），用唯一系统名避免受其他测试数据影响
        assert await _list_plan_names(
            client, auth,
            q(rule("system_name", "eq", A), rule("system_name", "eq", C, connector="or")),
        ) == {A, C}
        # 数字比较与区间（限定专属部门）
        assert await _list_plan_names(client, auth, q(dept, rule("est_mandays", "gte", 3))) == {A}
        assert await _list_plan_names(client, auth, q(dept, rule("est_mandays", "between", [2, 3]))) == {A, C}
        # 日期字符串上界（严格小于），空值被排除
        assert await _list_plan_names(client, auth, q(dept, rule("receive_time", "lt", "2026-02-01"))) == {A}
        # 空值筛选
        assert await _list_plan_names(client, auth, q(dept, rule("retest_notice_time", "is_empty"))) == {A, C}

        # 派生字段：自动生成工单ID精确匹配
        target = next(p for p in plans if p["system_name"] == A)
        assert target["ticket_id"]
        assert await _list_plan_names(client, auth, q(rule("ticket_id", "eq", target["ticket_id"]))) == {A}

        # 关联字段：认领后按测试人员筛选（限定专属部门）
        await client.post(f"/api/v1/testing-plans/{target['id']}/claim", headers=auth)
        assert await _list_plan_names(client, auth, q(dept, rule("testers", "contains", "admin"))) == {A}
        assert await _list_plan_names(client, auth, q(dept, rule("testers", "contains", "admin", not_=True))) == {C}

        # 非法字段 / 不匹配操作符返回 400
        resp = await client.get("/api/v1/testing-plans", headers=auth,
                                params=q(rule("not_exist", "eq", 1)))
        assert resp.status_code == 400
        resp = await client.get("/api/v1/testing-plans", headers=auth,
                                params=q(rule("system_name", "gt", 1)))
        assert resp.status_code == 400

        # stats 端点应用同一套筛选条件
        resp = await client.get("/api/v1/testing-plans/stats", headers=auth,
                                params=q(dept))
        assert resp.status_code == 200
        assert resp.json()["total_plans"] == 2
    finally:
        for p in plans:
            await client.delete(f"/api/v1/testing-plans/{p['id']}", headers=auth)


async def test_testing_plan_workflow(client: AsyncClient, auth: dict):
    """测试计划工作台：认领/退出、录入漏洞统计重算、报告关联三方状态联动。"""
    resp = await client.post(
        "/api/v1/testing-plans", headers=auth,
        json={"system_name": "工作台系统", "test_type": "渗透测试", "department": "研发部"},
    )
    assert resp.status_code == 200, resp.text
    plan_id = resp.json()["id"]
    assert resp.json()["status"] == 10

    # 认领：当前用户加入测试人员，未测试自动进入初测中
    resp = await client.post(f"/api/v1/testing-plans/{plan_id}/claim", headers=auth)
    assert resp.status_code == 200, resp.text
    plan = resp.json()
    assert plan["status"] == 20
    assert "admin" in [u["username"] for u in plan["testers"]]

    # 认领幂等：重复调用不重复添加
    resp = await client.post(f"/api/v1/testing-plans/{plan_id}/claim", headers=auth)
    assert len(resp.json()["testers"]) == 1

    # 带计划录入漏洞：统计按等级自动重算
    resp = await client.post("/api/v1/assets", headers=auth, json={"name": "工作台资产"})
    asset_id = resp.json()["id"]
    resp = await client.post(
        "/api/v1/vulns/batch", headers=auth,
        json={
            "asset_ids": [asset_id],
            "vulns": [
                {"title": "计划漏洞A", "level": 20, "testing_plan_id": plan_id},
                {"title": "计划漏洞B", "level": 30, "testing_plan_id": plan_id},
            ],
        },
    )
    assert resp.status_code == 200, resp.text
    vul_a, vul_b = [v["id"] for v in resp.json()]
    plan = await _get_plan(client, auth, plan_id)
    assert (plan["stat_high"], plan["stat_medium"]) == (1, 1)
    assert {v["id"] for v in plan["vuls"]} == {vul_a, vul_b}

    # 不存在的计划被拒绝
    resp = await client.post(
        "/api/v1/vulns", headers=auth, json={"title": "坏计划", "testing_plan_id": 999999},
    )
    assert resp.status_code == 400

    # 生成报告并关联计划：报告带 testing_plan_id，计划进入等待复测
    resp = await client.post(
        "/api/v1/reports/from-vulns", headers=auth,
        json={"title": "工作台报告", "vul_ids": [vul_a, vul_b], "testing_plan_id": plan_id},
    )
    assert resp.status_code == 200, resp.text
    report_id = resp.json()["id"]
    assert resp.json()["testing_plan_id"] == plan_id
    plan = await _get_plan(client, auth, plan_id)
    assert plan["status"] == 30
    assert plan["first_test_done_time"]

    # 发起复测：计划进入复测中，漏洞进入复测中
    resp = await client.post(f"/api/v1/reports/{report_id}/retest", headers=auth)
    assert resp.status_code == 200, resp.text
    plan = await _get_plan(client, auth, plan_id)
    assert plan["status"] == 50
    for vid in (vul_a, vul_b):
        vul = (await client.get(f"/api/v1/vulns/{vid}", headers=auth)).json()
        assert vul["status"] == 55

    # 部分处理完：报告与计划均未完成
    resp = await client.post(
        f"/api/v1/vulns/{vul_a}/transition", headers=auth,
        json={"status": 60, "retest_html": "<p>复测通过</p>"},
    )
    assert resp.status_code == 200
    plan = await _get_plan(client, auth, plan_id)
    assert plan["status"] == 50

    # 全部已修复/已忽略：报告保持草稿（需求6），计划复测完成并记完成时间
    resp = await client.post(
        f"/api/v1/vulns/{vul_b}/transition", headers=auth, json={"status": 20},
    )
    assert resp.status_code == 200
    report = (await client.get(f"/api/v1/reports/{report_id}", headers=auth)).json()
    assert report["status"] == "draft"
    plan = await _get_plan(client, auth, plan_id)
    assert plan["status"] == 60
    assert plan["retest_done_time"]

    # 非管理员权限边界：状态修改与录入漏洞仅限认领者
    resp = await client.post(
        "/api/v1/roles", headers=auth,
        json={"name": "计划测试员", "permissions": ["special:manage", "vuln:submit"], "remark": ""},
    )
    role_id = resp.json()["id"]
    resp = await client.post(
        "/api/v1/users", headers=auth,
        json={"username": "plan_tester", "password": "Tester@123", "realname": "计划测试员",
              "email": "", "phone": "", "is_active": True, "role_id": role_id},
    )
    assert resp.status_code == 200, resp.text
    resp = await client.post(
        "/api/v1/auth/login", data={"username": "plan_tester", "password": "Tester@123"},
    )
    auth2 = {"Authorization": f"Bearer {resp.json()['access_token']}"}

    plan_body = {k: plan[k] for k in (
        "system_name", "test_type", "department", "receive_time", "first_test_done_time",
        "status", "retest_notice_time", "retest_done_time",
        "stat_critical", "stat_high", "stat_medium", "stat_low", "brief", "detail",
    )}

    # 未认领：修改状态 403，录入漏洞 403，但基本信息编辑放行
    resp = await client.put(
        f"/api/v1/testing-plans/{plan_id}", headers=auth2, json={**plan_body, "status": 40},
    )
    assert resp.status_code == 403
    resp = await client.post(
        "/api/v1/vulns", headers=auth2, json={"title": "越权录入", "testing_plan_id": plan_id},
    )
    assert resp.status_code == 403
    resp = await client.put(
        f"/api/v1/testing-plans/{plan_id}", headers=auth2,
        json={**plan_body, "department": "研发一部"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["department"] == "研发一部"

    # 认领后可修改状态；退出认领后再改状态回到 403
    resp = await client.post(f"/api/v1/testing-plans/{plan_id}/claim", headers=auth2)
    assert len(resp.json()["testers"]) == 2
    # 当前计划已处于复测完成(60)，认领后改回复测中(50)为合法流转
    resp = await client.put(
        f"/api/v1/testing-plans/{plan_id}", headers=auth2, json={**plan_body, "status": 50},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == 50
    resp = await client.post(f"/api/v1/testing-plans/{plan_id}/quit", headers=auth2)
    assert "plan_tester" not in [u["username"] for u in resp.json()["testers"]]
    # 退出认领后修改状态（60 为合法目标但无认领权限）回到 403
    resp = await client.put(
        f"/api/v1/testing-plans/{plan_id}", headers=auth2, json={**plan_body, "status": 60},
    )
    assert resp.status_code == 403


async def test_testing_plan_detail(client: AsyncClient, auth: dict):
    """单条计划详情端点：返回关联字段；不存在 404；无 special:manage 权限 403。"""
    resp = await client.post(
        "/api/v1/testing-plans", headers=auth,
        json={"system_name": "详情端点系统", "test_type": "渗透测试"},
    )
    plan_id = resp.json()["id"]
    resp = await client.get(f"/api/v1/testing-plans/{plan_id}", headers=auth)
    assert resp.status_code == 200, resp.text
    detail = resp.json()
    assert detail["id"] == plan_id
    for key in ("testers", "vuls", "reports", "retest_rounds", "retest_round_count"):
        assert key in detail

    resp = await client.get("/api/v1/testing-plans/999999", headers=auth)
    assert resp.status_code == 404

    # 无 special:manage 权限的用户被拒绝
    resp = await client.post(
        "/api/v1/roles", headers=auth,
        json={"name": "无专项权限", "permissions": ["vuln:submit"], "remark": ""},
    )
    role_id = resp.json()["id"]
    resp = await client.post(
        "/api/v1/users", headers=auth,
        json={"username": "no_special", "password": "Tester@123", "realname": "无专项",
              "email": "", "phone": "", "is_active": True, "role_id": role_id},
    )
    assert resp.status_code == 200, resp.text
    resp = await client.post(
        "/api/v1/auth/login", data={"username": "no_special", "password": "Tester@123"},
    )
    auth2 = {"Authorization": f"Bearer {resp.json()['access_token']}"}
    resp = await client.get(f"/api/v1/testing-plans/{plan_id}", headers=auth2)
    assert resp.status_code == 403


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


async def test_dict_options(client: AsyncClient, auth: dict):
    """测试类型字典：预设种子 + 下拉新增持久化 + 重名拒绝。"""
    resp = await client.get("/api/v1/dict/test_type", headers=auth)
    assert resp.status_code == 200
    names = [o["name"] for o in resp.json()]
    assert names[:5] == ["加电上线", "互联网自主测试", "办公网自主测试", "CHBN项目测试", "品质测评"]

    # 新增：去空格后入库
    resp = await client.post("/api/v1/dict/test_type", headers=auth, json={"name": " 红蓝对抗 "})
    assert resp.status_code == 200, resp.text
    assert resp.json()["name"] == "红蓝对抗"

    # 重名 / 空名拒绝
    resp = await client.post("/api/v1/dict/test_type", headers=auth, json={"name": "红蓝对抗"})
    assert resp.status_code == 400
    resp = await client.post("/api/v1/dict/test_type", headers=auth, json={"name": "  "})
    assert resp.status_code == 400

    resp = await client.get("/api/v1/dict/test_type", headers=auth)
    assert "红蓝对抗" in [o["name"] for o in resp.json()]

    # 未登录拒绝
    resp = await client.get("/api/v1/dict/test_type")
    assert resp.status_code == 401


async def test_group_create_by_special_manage(client: AsyncClient, auth: dict):
    """测试计划「所属部门」下拉新增：special:manage 角色可创建组织，重名拒绝。"""
    resp = await client.post(
        "/api/v1/roles", headers=auth,
        json={"name": "专项管理角色", "permissions": ["special:manage"], "remark": ""},
    )
    role_id = resp.json()["id"]
    resp = await client.post(
        "/api/v1/users", headers=auth,
        json={"username": "special_user", "password": "Sp@123456", "realname": "专项用户",
              "email": "", "phone": "", "is_active": True, "role_id": role_id},
    )
    assert resp.status_code == 200, resp.text
    resp = await client.post(
        "/api/v1/auth/login", data={"username": "special_user", "password": "Sp@123456"},
    )
    auth_sp = {"Authorization": f"Bearer {resp.json()['access_token']}"}

    resp = await client.post("/api/v1/groups", headers=auth_sp, json={"name": "网络安全部", "remark": ""})
    assert resp.status_code == 200, resp.text
    resp = await client.post("/api/v1/groups", headers=auth_sp, json={"name": "网络安全部", "remark": ""})
    assert resp.status_code == 400
    resp = await client.get("/api/v1/groups", headers=auth_sp)
    assert "网络安全部" in [g["name"] for g in resp.json()]


async def test_group_owner_fields(client: AsyncClient, auth: dict):
    """组织负责人信息：改由「组织成员」管理（姓名/电话/邮箱 CRUD）。"""
    resp = await client.post(
        "/api/v1/groups", headers=auth,
        json={"name": "负责人测试部", "remark": ""},
    )
    assert resp.status_code == 200, resp.text
    group = resp.json()
    assert "owner_name" not in group  # 单字段 owner 已移除，改为组织成员承载

    # 添加组织成员
    resp = await client.post(
        f"/api/v1/groups/{group['id']}/members", headers=auth,
        json={"name": "赵六", "phone": "13700000000", "email": "zhaoliu@example.com"},
    )
    assert resp.status_code == 200, resp.text
    member = resp.json()
    assert member["name"] == "赵六"
    assert member["email"] == "zhaoliu@example.com"

    # 更新组织成员
    resp = await client.put(
        f"/api/v1/groups/{group['id']}/members/{member['id']}", headers=auth,
        json={"name": "钱七", "phone": "", "email": ""},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["name"] == "钱七"
    assert resp.json()["phone"] == ""

    # 删除组织成员
    members = (await client.get(f"/api/v1/groups/{group['id']}/members", headers=auth)).json()
    assert [m["name"] for m in members] == ["钱七"]
    resp = await client.delete(
        f"/api/v1/groups/{group['id']}/members/{member['id']}", headers=auth,
    )
    assert resp.status_code == 200
    members = (await client.get(f"/api/v1/groups/{group['id']}/members", headers=auth)).json()
    assert members == []


async def test_retest_round_tracking(client: AsyncClient, auth: dict):
    """复测轮次统计：手动流转记轮、重复流转不重复计数、报告发起复测强制开新轮、闭环打完成点。"""
    resp = await client.post(
        "/api/v1/testing-plans", headers=auth,
        json={"system_name": "轮次系统", "department": "轮次部门"},
    )
    plan_id = resp.json()["id"]
    assert resp.json()["retest_round_count"] == 0
    await client.post(f"/api/v1/testing-plans/{plan_id}/claim", headers=auth)

    plan = await _get_plan(client, auth, plan_id)
    body = {k: plan[k] for k in (
        "system_name", "test_type", "department", "receive_time", "first_test_done_time",
        "status", "retest_notice_time", "retest_done_time",
        "stat_critical", "stat_high", "stat_medium", "stat_low", "brief", "detail",
    )}

    # 手动流转到复测中：记第 1 轮（需经初测完成 30，再进入复测中 50）
    resp = await client.put(
        f"/api/v1/testing-plans/{plan_id}", headers=auth, json={**body, "status": 30},
    )
    assert resp.status_code == 200, resp.text
    resp = await client.put(
        f"/api/v1/testing-plans/{plan_id}", headers=auth, json={**body, "status": 50},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["retest_round_count"] == 1
    assert resp.json()["retest_rounds"][0]["done_time"] is None

    # 反复流转（50→30→50）：已有进行中轮次不重复计数
    await client.put(f"/api/v1/testing-plans/{plan_id}", headers=auth, json={**body, "status": 30})
    resp = await client.put(
        f"/api/v1/testing-plans/{plan_id}", headers=auth, json={**body, "status": 50},
    )
    assert resp.json()["retest_round_count"] == 1

    # 报告实际发起复测：结束上一轮并强制开新轮
    resp = await client.post("/api/v1/assets", headers=auth, json={"name": "轮次资产"})
    asset_id = resp.json()["id"]
    resp = await client.post(
        "/api/v1/vulns/batch", headers=auth,
        json={
            "asset_ids": [asset_id],
            "vulns": [
                {"title": "轮次漏洞A", "level": 20, "testing_plan_id": plan_id},
                {"title": "轮次漏洞B", "level": 30, "testing_plan_id": plan_id},
            ],
        },
    )
    vul_a, vul_b = [v["id"] for v in resp.json()]
    resp = await client.post(
        "/api/v1/reports/from-vulns", headers=auth,
        json={"title": "轮次报告", "vul_ids": [vul_a, vul_b], "testing_plan_id": plan_id},
    )
    report_id = resp.json()["id"]
    resp = await client.post(f"/api/v1/reports/{report_id}/retest", headers=auth)
    assert resp.status_code == 200, resp.text
    plan = await _get_plan(client, auth, plan_id)
    assert plan["retest_round_count"] == 2
    rounds = plan["retest_rounds"]
    assert rounds[0]["round_no"] == 1 and rounds[0]["done_time"] is not None
    assert rounds[1]["round_no"] == 2 and rounds[1]["done_time"] is None
    assert "轮次报告" in rounds[1]["source"]

    # 再次发起复测：已处于复测中的漏洞同样视为复测流程已发起（force=True），强制开新一轮
    resp = await client.post(f"/api/v1/reports/{report_id}/retest", headers=auth)
    plan = await _get_plan(client, auth, plan_id)
    assert plan["retest_round_count"] == 3

    # 全部闭环：计划复测完成，当前轮打完成点
    await client.post(
        f"/api/v1/vulns/{vul_a}/transition", headers=auth,
        json={"status": 60, "retest_html": "<p>复测通过</p>"},
    )
    await client.post(f"/api/v1/vulns/{vul_b}/transition", headers=auth, json={"status": 20})
    plan = await _get_plan(client, auth, plan_id)
    assert plan["status"] == 60
    assert plan["retest_rounds"][1]["done_time"] is not None


async def test_dashboard_by_department(client: AsyncClient, auth: dict):
    """安全态势部门维度：提测次数 / 发现漏洞（含手填补充） / 修复率。"""
    # 无关联漏洞的计划：发现数取手填统计，修复率为空
    resp = await client.post(
        "/api/v1/testing-plans", headers=auth,
        json={"system_name": "看板系统", "department": "看板部门", "stat_high": 2, "stat_low": 1},
    )
    assert resp.status_code == 200, resp.text

    stats = (await client.get("/api/v1/dashboard/stats", headers=auth)).json()
    assert "by_department" in stats
    dept = next(d for d in stats["by_department"] if d["department"] == "看板部门")
    assert dept["plans"] == 1
    assert dept["vulns"] == 3
    assert dept["fixed"] == 0
    assert dept["fix_rate"] is None

    # 有关联漏洞的计划（test_retest_round_tracking：1 已修复 + 1 已忽略）
    dept2 = next(d for d in stats["by_department"] if d["department"] == "轮次部门")
    assert dept2["plans"] == 1
    assert dept2["vulns"] == 2
    assert dept2["fixed"] == 1
    assert dept2["fix_rate"] == 50.0


async def test_testing_plan_filter_stats_export(client: AsyncClient, auth: dict):
    """测试计划筛选（类型/部门/时间范围）、多维度统计与 Excel 双 sheet 导出。"""
    from openpyxl import load_workbook

    tag = "筛选统计专用部门"
    # 三条计划：不同状态 / 类型 / 接收时间，便于区分筛选与统计口径
    plans = [
        {"system_name": "过滤系统A", "department": tag, "test_type": "黑盒测试",
         "receive_time": "2026-01-15", "status": 20},   # 初测中
        {"system_name": "过滤系统B", "department": tag, "test_type": "白盒测试",
         "receive_time": "2026-03-20", "status": 60},   # 复测完成
        {"system_name": "过滤系统C", "department": tag, "test_type": "黑盒测试",
         "receive_time": "2026-06-10", "status": 10},   # 未测试
    ]
    for p in plans:
        resp = await client.post("/api/v1/testing-plans", headers=auth, json=p)
        assert resp.status_code == 200, resp.text

    # 部门 + 类型精确筛选
    resp = await client.get(
        "/api/v1/testing-plans", headers=auth,
        params={"department": tag, "test_type": "黑盒测试"},
    )
    names = {i["system_name"] for i in resp.json()["items"]}
    assert names == {"过滤系统A", "过滤系统C"}

    # 时间范围筛选（按需求接收时间）
    resp = await client.get(
        "/api/v1/testing-plans", headers=auth,
        params={"department": tag, "receive_from": "2026-02-01", "receive_to": "2026-04-01"},
    )
    names = {i["system_name"] for i in resp.json()["items"]}
    assert names == {"过滤系统B"}

    # 统计口径：本部门下 3 条计划
    resp = await client.get("/api/v1/testing-plans/stats", headers=auth, params={"department": tag})
    assert resp.status_code == 200, resp.text
    stats = resp.json()
    assert stats["total_plans"] == 3
    assert stats["retest_done_plans"] == 1          # 仅 B 为复测完成
    assert stats["first_test_count"] == 2           # A(20)+B(60) 达到初测中及以上
    assert stats["total_test_count"] == stats["first_test_count"] + stats["retest_count"]
    status_counts = {r["status"]: r["count"] for r in stats["by_status"]}
    assert status_counts == {10: 1, 20: 1, 60: 1}
    assert isinstance(stats["vulns_by_month"], list)

    # pending 待办流程筛选：仅 未测试(10)/初测中(20)/复测中(50)，复测完成(60) 被排除
    resp = await client.get(
        "/api/v1/testing-plans", headers=auth,
        params={"department": tag, "pending": True},
    )
    names = {i["system_name"] for i in resp.json()["items"]}
    assert names == {"过滤系统A", "过滤系统C"}
    assert all(i["status"] in (10, 20, 50) for i in resp.json()["items"])

    # pending 与单状态筛选同时传参时按 AND 处理：无交集则空结果
    resp = await client.get(
        "/api/v1/testing-plans", headers=auth,
        params={"department": tag, "pending": True, "status": 60},
    )
    assert resp.json()["total"] == 0

    # pending 统计口径与列表一致：本部门待办 2 条
    pending_stats = (await client.get(
        "/api/v1/testing-plans/stats", headers=auth, params={"department": tag, "pending": True},
    )).json()
    assert pending_stats["total_plans"] == 2
    assert pending_stats["retest_done_plans"] == 0

    # 空结果集：全 0，不报错
    empty = (await client.get(
        "/api/v1/testing-plans/stats", headers=auth, params={"department": "不存在的部门XYZ"},
    )).json()
    assert empty["total_plans"] == 0
    assert empty["total_test_count"] == 0

    # 导出：双 sheet，可被 openpyxl 回读
    resp = await client.get("/api/v1/testing-plans/export", headers=auth, params={"department": tag})
    assert resp.status_code == 200
    assert resp.content[:2] == b"PK"
    wb = load_workbook(BytesIO(resp.content))
    assert "测试计划" in wb.sheetnames
    assert "统计汇总" in wb.sheetnames
    detail_rows = list(wb["测试计划"].iter_rows(values_only=True))
    assert len(detail_rows) == 4  # 表头 + 3 行
    assert detail_rows[0][1] == "测试计划名称"  # 表头第二列与 PLAN_EXCEL_HEADERS 一致

    # 导出同样支持 pending 筛选：仅 2 条待办计划
    resp = await client.get(
        "/api/v1/testing-plans/export", headers=auth,
        params={"department": tag, "pending": True},
    )
    assert resp.status_code == 200
    wb2 = load_workbook(BytesIO(resp.content))
    pending_rows = list(wb2["测试计划"].iter_rows(values_only=True))
    assert len(pending_rows) == 3  # 表头 + 2 行
    assert "统计汇总" in wb2.sheetnames


async def test_testing_plan_mandays_and_reports(client: AsyncClient, auth: dict):
    """人天字段、人天统计（剩余预估人天=未测试计划预估人天之和）与计划反向展示关联报告。"""
    from openpyxl import load_workbook

    tag = "人天统计专用部门"
    plans = [
        {"system_name": "人天系统A", "department": tag, "status": 10,
         "est_mandays": 3, "actual_mandays": 0},     # 未测试 → 计入剩余
        {"system_name": "人天系统B", "department": tag, "status": 20,
         "est_mandays": 5, "actual_mandays": 2.5},
        {"system_name": "人天系统C", "department": tag, "status": 60,
         "est_mandays": 2, "actual_mandays": 4},
    ]
    plan_ids = []
    for p in plans:
        resp = await client.post("/api/v1/testing-plans", headers=auth, json=p)
        assert resp.status_code == 200, resp.text
        assert resp.json()["est_mandays"] == p["est_mandays"]
        assert resp.json()["actual_mandays"] == p["actual_mandays"]
        plan_ids.append(resp.json()["id"])

    # 人天统计：总预估/总实际/剩余预估（仅未测试状态）
    stats = (await client.get(
        "/api/v1/testing-plans/stats", headers=auth, params={"department": tag},
    )).json()
    assert stats["est_mandays_total"] == 10
    assert stats["actual_mandays_total"] == 6.5
    assert stats["remaining_est_mandays"] == 3

    # 导出明细含人天列，汇总含人天指标
    resp = await client.get("/api/v1/testing-plans/export", headers=auth, params={"department": tag})
    wb = load_workbook(BytesIO(resp.content))
    detail_rows = list(wb["测试计划"].iter_rows(values_only=True))
    header = list(detail_rows[0])
    assert "预估人天" in header and "实际人天" in header
    est_col = header.index("预估人天")
    assert {r[est_col] for r in detail_rows[1:]} == {3, 5, 2}
    summary = {r[0]: r[1] for r in wb["统计汇总"].iter_rows(values_only=True) if r[0]}
    assert summary["预估人天总计"] == 10
    assert summary["实际人天总计"] == 6.5
    assert summary["剩余预估人天（未测试）"] == 3

    # 计划反向展示关联报告：录入漏洞→生成报告后 reports 列表可见
    plan_b = plan_ids[1]
    # 严格认领：需先认领计划才能建计划漏洞
    await client.post(f"/api/v1/testing-plans/{plan_b}/claim", headers=auth)
    resp = await client.post("/api/v1/assets", headers=auth, json={"name": "人天反向资产"})
    asset_id = resp.json()["id"]
    resp = await client.post(
        "/api/v1/vulns", headers=auth,
        json={"title": "人天反向漏洞", "level": 20, "asset_ids": [asset_id],
              "testing_plan_id": plan_b},
    )
    vul_id = resp.json()["id"]
    resp = await client.post(
        "/api/v1/reports/from-vulns", headers=auth,
        json={"title": "人天反向报告", "vul_ids": [vul_id], "testing_plan_id": plan_b},
    )
    assert resp.status_code == 200, resp.text
    report_id = resp.json()["id"]

    plan = await _get_plan(client, auth, plan_b)
    assert [r["id"] for r in plan["reports"]] == [report_id]
    assert plan["reports"][0]["title"] == "人天反向报告"
    assert plan["reports"][0]["status"] == "draft"


async def test_testing_plan_excel_import(client: AsyncClient, auth: dict):
    """测试计划 Excel 导入：模板下载、按 ID 更新、无 ID 新增、非法行报错。"""
    from openpyxl import Workbook

    # 模板下载
    resp = await client.get("/api/v1/testing-plans/import/template", headers=auth)
    assert resp.status_code == 200
    assert resp.content[:2] == b"PK"

    # 先建一条计划供导入更新
    resp = await client.post(
        "/api/v1/testing-plans", headers=auth,
        json={"system_name": "导入前系统", "department": "导入专用部门", "est_mandays": 1},
    )
    exist_id = resp.json()["id"]

    # 表头与模板一致（PLAN_EXCEL_HEADERS 20 列，含「测试计划名称」列）
    headers_row = ["ID", "测试计划名称", "测试系统", "测试类型", "所属部门", "工单ID",
                   "工单提起时间", "状态", "测试人员", "需求接收", "初测完成", "复测通知",
                   "复测完成", "预估人天", "实际人天", "超危数", "高危数", "中危数",
                   "低危数", "复测轮数"]
    wb = Workbook()
    ws = wb.active
    ws.append(headers_row)
    # 无 ID → 新增（测试人员按用户名匹配 admin）
    ws.append(["", "", "导入新增系统", "渗透测试", "导入专用部门", "", "",
               "初测中", "admin", "2025-11-01", "2025-11-05", "", "", 3.5, 1, 1, 2, 0, 0, 0])
    # 有 ID → 更新同一条计划
    ws.append([exist_id, "", "导入后系统", "白盒测试", "导入专用部门", "", "",
               "复测完成", "", "2025-10-01", "", "", "2025-12-31", 6, 5.5, 0, 0, 0, 0, 0])
    # 缺测试系统 → 失败
    ws.append(["", "", "", "黑盒测试", "导入专用部门", "", "", "", "", "", "", "", "",
               0, 0, 0, 0, 0, 0, 0])
    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)

    resp = await client.post(
        "/api/v1/testing-plans/import", headers=auth,
        files={"file": ("plans.xlsx", buf,
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert resp.status_code == 200, resp.text
    result = resp.json()
    assert result["total"] == 3
    assert result["created"] == 1
    assert result["updated"] == 1
    assert result["failed"] == 1
    assert "测试系统为必填项" in result["errors"][0]

    # 新增行校验：状态/人天/测试人员匹配
    resp = await client.get(
        "/api/v1/testing-plans", headers=auth, params={"search": "导入新增系统"},
    )
    created = resp.json()["items"][0]
    assert created["status"] == 20
    assert created["est_mandays"] == 3.5
    assert created["stat_critical"] == 1 and created["stat_high"] == 2
    assert "admin" in [u["username"] for u in created["testers"]]

    # 更新行校验：同 ID 字段被覆盖
    updated = await _get_plan(client, auth, exist_id)
    assert updated["system_name"] == "导入后系统"
    assert updated["status"] == 60
    assert updated["est_mandays"] == 6
    assert updated["actual_mandays"] == 5.5

    # 非 xlsx 拒绝
    resp = await client.post(
        "/api/v1/testing-plans/import", headers=auth,
        files={"file": ("bad.txt", b"hello", "text/plain")},
    )
    assert resp.status_code == 400


async def test_dashboard_event_filters(client: AsyncClient, auth: dict):
    """安全态势按事件多维筛选：部门/等级/来源/时间范围。"""
    dept = "态势筛选部门"
    resp = await client.post(
        "/api/v1/testing-plans", headers=auth,
        json={"system_name": "态势筛选系统", "department": dept},
    )
    plan_id = resp.json()["id"]
    # 严格认领：需先认领计划才能批量建计划漏洞
    await client.post(f"/api/v1/testing-plans/{plan_id}/claim", headers=auth)
    resp = await client.post("/api/v1/assets", headers=auth, json={"name": "态势筛选资产"})
    asset_id = resp.json()["id"]
    resp = await client.post(
        "/api/v1/vulns/batch", headers=auth,
        json={
            "asset_ids": [asset_id],
            "vulns": [
                {"title": "态势高危漏洞", "level": 20, "source": 10, "testing_plan_id": plan_id},
                {"title": "态势中危漏洞", "level": 30, "source": 20, "testing_plan_id": plan_id},
            ],
        },
    )
    assert resp.status_code == 200, resp.text

    # 部门筛选：仅统计该部门计划关联的 2 条漏洞
    stats = (await client.get(
        "/api/v1/dashboard/stats", headers=auth, params={"department": dept},
    )).json()
    assert stats["total_vulns"] == 2
    assert {x["name"] for x in stats["by_level"]} == {"高危", "中危"}
    assert [d["department"] for d in stats["by_department"]] == [dept]

    # 部门 + 等级
    stats = (await client.get(
        "/api/v1/dashboard/stats", headers=auth,
        params={"department": dept, "level": 20},
    )).json()
    assert stats["total_vulns"] == 1

    # 部门 + 来源
    stats = (await client.get(
        "/api/v1/dashboard/stats", headers=auth,
        params={"department": dept, "source": 20},
    )).json()
    assert stats["total_vulns"] == 1

    # 时间范围：未来区间无数据；包含今天则命中
    stats = (await client.get(
        "/api/v1/dashboard/stats", headers=auth,
        params={"department": dept, "date_from": "2099-01-01", "date_to": "2099-12-31"},
    )).json()
    assert stats["total_vulns"] == 0
    stats = (await client.get(
        "/api/v1/dashboard/stats", headers=auth,
        params={"department": dept, "date_from": "2000-01-01", "date_to": "2099-12-31"},
    )).json()
    assert stats["total_vulns"] == 2


async def test_retest_record_sync_to_vul(client: AsyncClient, auth: dict):
    """复测记录增/改/删同步聚合到 Vul.retest_html（详情页/报告读取口径）。"""
    resp = await client.post(
        "/api/v1/vulns", headers=auth, json={"title": "复测同步漏洞", "level": 20},
    )
    vul_id = resp.json()["id"]

    # 新增一条记录：retest_html 同步为记录内容
    resp = await client.post(
        f"/api/v1/vulns/{vul_id}/retests", headers=auth,
        json={"content_html": "<p>第一次复测仍存在</p>", "content_json": None},
    )
    assert resp.status_code == 200, resp.text
    rec1_id = resp.json()["id"]
    vul = (await client.get(f"/api/v1/vulns/{vul_id}", headers=auth)).json()
    assert vul["retest_html"] == "<p>第一次复测仍存在</p>"

    # 第二条记录：聚合并带"复测记录 N"标题
    resp = await client.post(
        f"/api/v1/vulns/{vul_id}/retests", headers=auth,
        json={"content_html": "<p>第二次复测已修复</p>", "content_json": None},
    )
    rec2_id = resp.json()["id"]
    vul = (await client.get(f"/api/v1/vulns/{vul_id}", headers=auth)).json()
    assert "复测记录 1" in vul["retest_html"] and "复测记录 2" in vul["retest_html"]
    assert "第一次复测仍存在" in vul["retest_html"]
    assert "第二次复测已修复" in vul["retest_html"]

    # 更新记录：聚合内容跟随变化
    resp = await client.put(
        f"/api/v1/vulns/{vul_id}/retests/{rec2_id}", headers=auth,
        json={"content_html": "<p>第二次复测部分修复</p>", "content_json": None},
    )
    assert resp.status_code == 200, resp.text
    vul = (await client.get(f"/api/v1/vulns/{vul_id}", headers=auth)).json()
    assert "第二次复测部分修复" in vul["retest_html"]
    assert "第二次复测已修复" not in vul["retest_html"]

    # 删除一条：回到单条内容（无编号标题）
    resp = await client.delete(f"/api/v1/vulns/{vul_id}/retests/{rec2_id}", headers=auth)
    assert resp.status_code == 200
    vul = (await client.get(f"/api/v1/vulns/{vul_id}", headers=auth)).json()
    assert vul["retest_html"] == "<p>第一次复测仍存在</p>"

    # 全部删除：retest_html 清空
    resp = await client.delete(f"/api/v1/vulns/{vul_id}/retests/{rec1_id}", headers=auth)
    assert resp.status_code == 200
    vul = (await client.get(f"/api/v1/vulns/{vul_id}", headers=auth)).json()
    assert not vul["retest_html"]


async def test_retest_failed_back_to_fixing(client: AsyncClient, auth: dict):
    """复测未通过打回：50 → 55 → 50 后 status=50 且 is_retest=true（前端据此展示"复测未通过"）。"""
    resp = await client.post(
        "/api/v1/vulns", headers=auth, json={"title": "复测打回漏洞", "level": 20},
    )
    vul_id = resp.json()["id"]

    for status in (50, 55):
        resp = await client.post(
            f"/api/v1/vulns/{vul_id}/transition", headers=auth, json={"status": status},
        )
        assert resp.status_code == 200, resp.text
    # 复测未通过回修复中：必须填写复测详情
    resp = await client.post(
        f"/api/v1/vulns/{vul_id}/transition", headers=auth,
        json={"status": 50, "retest_html": "<p>复测发现仍可利用</p>"},
    )
    assert resp.status_code == 200, resp.text

    vul = (await client.get(f"/api/v1/vulns/{vul_id}", headers=auth)).json()
    assert vul["status"] == 50
    assert vul["is_retest"] is True


async def test_vuln_status_retest_guard(client: AsyncClient, auth: dict):
    """复测结论校验：修复中不可直接变已修复；复测中→已修复/复测未通过必须填写复测内容。"""
    resp = await client.post("/api/v1/vulns", headers=auth, json={"title": "复测守卫漏洞", "level": 20})
    vul_id = resp.json()["id"]
    # 进入修复中
    resp = await client.post(f"/api/v1/vulns/{vul_id}/transition", headers=auth, json={"status": 50})
    assert resp.status_code == 200

    # 报告编辑页下拉（fields 接口）从修复中直接改已修复 → 拒绝（必须经过复测中）
    resp = await client.patch(f"/api/v1/vulns/{vul_id}/fields", headers=auth, json={"status": 60})
    assert resp.status_code == 400

    # 进入复测中
    resp = await client.post(f"/api/v1/vulns/{vul_id}/transition", headers=auth, json={"status": 55})
    assert resp.status_code == 200

    # 复测中→已修复但未填写复测内容 → 拒绝
    resp = await client.post(f"/api/v1/vulns/{vul_id}/transition", headers=auth, json={"status": 60})
    assert resp.status_code == 400

    # 复测中→复测未通过（回修复中）但未填写复测详情 → 拒绝
    resp = await client.post(f"/api/v1/vulns/{vul_id}/transition", headers=auth, json={"status": 50})
    assert resp.status_code == 400

    # 填写复测内容后可正常闭环
    resp = await client.post(
        f"/api/v1/vulns/{vul_id}/transition", headers=auth,
        json={"status": 60, "retest_html": "<p>复测已修复</p>"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == 60


async def test_ticket_seq_increment_no_reuse(client: AsyncClient, auth: dict):
    """工单ID自动分配采用「当日最大编号+1」：删除/释放的编号不复用，仅手动可选用。"""
    body = {"department": "递增部门", "receive_time": "2026-01-01"}

    resp = await client.post(
        "/api/v1/testing-plans", headers=auth, json={**body, "system_name": "递增系统A"},
    )
    assert resp.status_code == 200, resp.text
    plan_a = resp.json()
    assert plan_a["ticket_id"] == "20260101-1"

    resp = await client.post(
        "/api/v1/testing-plans", headers=auth, json={**body, "system_name": "递增系统B"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["ticket_id"] == "20260101-2"

    # 删除占用 20260101-1 的计划后，自动分配不复用空洞，继续递增到 3
    resp = await client.delete(f"/api/v1/testing-plans/{plan_a['id']}", headers=auth)
    assert resp.status_code == 200, resp.text
    resp = await client.post(
        "/api/v1/testing-plans", headers=auth, json={**body, "system_name": "递增系统C"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["ticket_id"] == "20260101-3"

    # 被释放的 20260101-1 仍可手动指定给新工单
    resp = await client.post(
        "/api/v1/testing-plans", headers=auth,
        json={**body, "system_name": "递增系统D", "ticket_id_manual": "20260101-1"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["ticket_id"] == "20260101-1"


async def test_ticket_id_manual_occupancy_and_ghost(client: AsyncClient, auth: dict):
    """工单编号占用口径统一：自动分配跳过 manual 占用；manual 记录底层 seq 不产生幽灵占用。"""
    body = {"department": "占用部门", "receive_time": "2026-07-30"}

    # A 手动指定 20260730-2（其 ticket_seq=0，不参与自动分配）
    resp = await client.post(
        "/api/v1/testing-plans", headers=auth,
        json={**body, "system_name": "占用系统A", "ticket_id_manual": "20260730-2"},
    )
    assert resp.status_code == 200, resp.text

    # 自动工单 B：max(纯自动 seq, manual N)=2 -> 新序号 3，编号 20260730-3（跳过 A 占用的 2）
    resp = await client.post("/api/v1/testing-plans", headers=auth, json={**body, "system_name": "占用系统B"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["ticket_id"] == "20260730-3"

    # 自动工单 C：max(3, 2)+1=4 -> 20260730-4（单调递增）
    resp = await client.post("/api/v1/testing-plans", headers=auth, json={**body, "system_name": "占用系统C"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["ticket_id"] == "20260730-4"

    # 幽灵占用场景：D 自动得到 20260730-5 后手动改为 20260730-88（底层 seq 保留 5）
    resp = await client.post("/api/v1/testing-plans", headers=auth, json={**body, "system_name": "占用系统D"})
    plan_d = resp.json()
    assert plan_d["ticket_id"] == "20260730-5"
    resp = await client.put(
        f"/api/v1/testing-plans/{plan_d['id']}", headers=auth,
        json={**body, "system_name": "占用系统D", "ticket_id_manual": "20260730-88"},
    )
    assert resp.status_code == 200, resp.text

    # E 手动指定 20260730-5（D 显示为 20260730-88，无任何工单显示 5）→ 应放行
    resp = await client.post(
        "/api/v1/testing-plans", headers=auth,
        json={**body, "system_name": "占用系统E", "ticket_id_manual": "20260730-5"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["ticket_id"] == "20260730-5"


async def test_create_retest_record_with_status(client: AsyncClient, auth: dict):
    """新增复测记录可同时调整漏洞状态：选结论须填复测内容，已修复/复测未通过均生效。"""
    # 准备：漏洞进入复测中
    resp = await client.post("/api/v1/vulns", headers=auth, json={"title": "复测状态联动漏洞", "level": 20})
    vul_id = resp.json()["id"]
    for status in (50, 55):
        resp = await client.post(f"/api/v1/vulns/{vul_id}/transition", headers=auth, json={"status": status})
        assert resp.status_code == 200, resp.text

    # 新增复测记录时选「已修复」但未填写内容 → 拒绝
    resp = await client.post(
        f"/api/v1/vulns/{vul_id}/retests", headers=auth,
        json={"content_html": "", "status": 60},
    )
    assert resp.status_code == 400

    # 新增复测记录时选「已修复」并填写内容 → 成功且状态流转为已修复
    resp = await client.post(
        f"/api/v1/vulns/{vul_id}/retests", headers=auth,
        json={"content_html": "<p>本次复测通过</p>", "content_json": None, "status": 60},
    )
    assert resp.status_code == 200, resp.text
    vul = (await client.get(f"/api/v1/vulns/{vul_id}", headers=auth)).json()
    assert vul["status"] == 60

    # 新漏洞复测未通过：新增复测记录时选「复测未修复」回修复中
    resp = await client.post("/api/v1/vulns", headers=auth, json={"title": "复测未通过联动漏洞", "level": 20})
    vul2 = resp.json()["id"]
    for status in (50, 55):
        resp = await client.post(f"/api/v1/vulns/{vul2}/transition", headers=auth, json={"status": status})
        assert resp.status_code == 200, resp.text
    resp = await client.post(
        f"/api/v1/vulns/{vul2}/retests", headers=auth,
        json={"content_html": "<p>复测仍存在</p>", "status": 50},
    )
    assert resp.status_code == 200, resp.text
    vul2_detail = (await client.get(f"/api/v1/vulns/{vul2}", headers=auth)).json()
    assert vul2_detail["status"] == 50
    assert vul2_detail["is_retest"] is True


async def test_report_section_contains_retest(client: AsyncClient, auth: dict):
    """含复测内容的漏洞生成报告：章节 content_html 嵌入复测详情。"""
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
    assert "复测详情" in section["content_html"]
    assert "复测发现仍可利用" in section["content_html"]


async def test_knowledge_crud_and_from_vul(client: AsyncClient, auth: dict):
    """漏洞知识库：upsert / 按类型查询 / 存为模板 / 删除。"""
    # 新建条目（vul_type=10 SQL注入类，以 meta 字典为准）
    resp = await client.post(
        "/api/v1/knowledge", headers=auth,
        json={"vulnerability_name": "SQL注入", "vul_type": 10, "severity_level": 10,
              "description_html": "<p>标准SQL注入描述</p>",
              "harm_html": "<p>可拖库</p>", "solution_html": "<p>参数化查询</p>",
              "references": ["https://owasp.org/Top10/"]},
    )
    assert resp.status_code == 200, resp.text
    entry = resp.json()
    assert entry["vulnerability_name"] == "SQL注入"
    assert entry["vul_type"] == 10
    assert entry["severity_level"] == 10
    assert entry["references"] == ["https://owasp.org/Top10/"]

    # 同名称再提交：覆盖而非新建（POST 为整体覆盖，未传字段取默认值）
    resp = await client.post(
        "/api/v1/knowledge", headers=auth,
        json={"vulnerability_name": "SQL注入", "vul_type": 10, "severity_level": 10,
              "description_html": "<p>描述V2</p>"},
    )
    assert resp.json()["id"] == entry["id"]
    assert resp.json()["description_html"] == "<p>描述V2</p>"

    # 同类型可存多条（不同名称）
    resp = await client.post(
        "/api/v1/knowledge", headers=auth,
        json={"vulnerability_name": "SQL盲注", "vul_type": 10, "severity_level": 20},
    )
    assert resp.status_code == 200, resp.text
    resp = await client.get("/api/v1/knowledge", headers=auth)
    assert len([e for e in resp.json() if e["vul_type"] == 10]) == 2

    # 按类型查询：返回列表（前端弹窗选择），危害等级最高的在前；未知类型 404
    resp = await client.get("/api/v1/knowledge/by-type/10", headers=auth)
    assert resp.status_code == 200
    items = resp.json()
    assert isinstance(items, list)
    assert items[0]["vulnerability_name"] == "SQL注入"
    resp = await client.get("/api/v1/knowledge/by-type/9999", headers=auth)
    assert resp.status_code == 200
    assert resp.json() == []

    # 未知类型/等级/空名称/非法参考链接拒绝
    resp = await client.post("/api/v1/knowledge", headers=auth,
                             json={"vulnerability_name": "x", "vul_type": 9999})
    assert resp.status_code == 400
    resp = await client.post("/api/v1/knowledge", headers=auth,
                             json={"vulnerability_name": "x", "vul_type": 10, "severity_level": 99})
    assert resp.status_code == 400
    resp = await client.post("/api/v1/knowledge", headers=auth,
                             json={"vulnerability_name": "   ", "vul_type": 10})
    assert resp.status_code == 422
    resp = await client.post("/api/v1/knowledge", headers=auth,
                             json={"vulnerability_name": "x", "vul_type": 10,
                                   "references": ["javascript:alert(1)"]})
    assert resp.status_code == 422

    # PUT 按 ID 编辑：改名、改等级；改为已存在名称被拒
    resp = await client.put(
        f"/api/v1/knowledge/{entry['id']}", headers=auth,
        json={"vulnerability_name": "SQL注入（联合查询）", "vul_type": 10, "severity_level": 20},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["vulnerability_name"] == "SQL注入（联合查询）"
    assert resp.json()["severity_level"] == 20
    resp = await client.put(
        f"/api/v1/knowledge/{entry['id']}", headers=auth,
        json={"vulnerability_name": "SQL盲注", "vul_type": 10},
    )
    assert resp.status_code == 400

    # 从已有漏洞存为模板：按标题作为名称 upsert，携带等级与描述/修复建议
    resp = await client.post(
        "/api/v1/vulns", headers=auth,
        json={"title": "知识库模板源漏洞", "level": 20, "vul_type": 10,
              "description_html": "<p>高质量描述</p>", "solution_html": "<p>高质量修复建议</p>"},
    )
    vul_id = resp.json()["id"]
    resp = await client.post(f"/api/v1/knowledge/from-vul/{vul_id}", headers=auth)
    assert resp.status_code == 200, resp.text
    assert resp.json()["vulnerability_name"] == "知识库模板源漏洞"
    assert resp.json()["severity_level"] == 20
    assert resp.json()["description_html"] == "<p>高质量描述</p>"
    assert resp.json()["solution_html"] == "<p>高质量修复建议</p>"

    # 未登录拒绝
    resp = await client.get("/api/v1/knowledge")
    assert resp.status_code == 401

    # 删除
    resp = await client.delete(f"/api/v1/knowledge/{entry['id']}", headers=auth)
    assert resp.status_code == 200
    resp = await client.get("/api/v1/knowledge", headers=auth)
    assert entry["id"] not in [e["id"] for e in resp.json()]


async def test_knowledge_batch_import_and_delete(client: AsyncClient, auth: dict):
    """漏洞知识库：批量导入（按名称 upsert）与批量删除。"""
    items = [
        {"vulnerability_name": "批量-SSRF", "vul_type": 75, "severity_level": 20,
         "description_html": "<p>SSRF描述</p>", "references": ["https://portswigger.net/web-security/ssrf"]},
        {"vulnerability_name": "批量-垂直越权", "vul_type": 40, "severity_level": 10},
        {"vulnerability_name": "批量-弱口令", "vul_type": 65, "severity_level": 20},
    ]
    resp = await client.post("/api/v1/knowledge/batch-import", headers=auth, json={"items": items})
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"created": 3, "updated": 0, "total": 3}

    # 再次导入：同名覆盖，新名新增
    items[0]["description_html"] = "<p>SSRF描述V2</p>"
    items.append({"vulnerability_name": "批量-未授权访问", "vul_type": 40, "severity_level": 20})
    resp = await client.post("/api/v1/knowledge/batch-import", headers=auth, json={"items": items})
    assert resp.json() == {"created": 1, "updated": 3, "total": 4}
    resp = await client.get("/api/v1/knowledge", headers=auth)
    batch_rows = [e for e in resp.json() if e["vulnerability_name"].startswith("批量-")]
    assert len(batch_rows) == 4
    assert next(e for e in batch_rows if e["vulnerability_name"] == "批量-SSRF")["description_html"] == "<p>SSRF描述V2</p>"

    # 批内重名 / 字典码非法：整批拒绝
    resp = await client.post("/api/v1/knowledge/batch-import", headers=auth, json={"items": [
        {"vulnerability_name": "重名", "vul_type": 10}, {"vulnerability_name": "重名", "vul_type": 15},
    ]})
    assert resp.status_code == 400
    resp = await client.post("/api/v1/knowledge/batch-import", headers=auth, json={"items": [
        {"vulnerability_name": "非法类型", "vul_type": 9999},
    ]})
    assert resp.status_code == 400
    resp = await client.post("/api/v1/knowledge/batch-import", headers=auth, json={"items": []})
    assert resp.status_code == 422

    # 批量删除（含不存在的 ID，忽略）
    ids = [e["id"] for e in batch_rows]
    resp = await client.post("/api/v1/knowledge/batch-delete", headers=auth,
                             json={"ids": ids + [999999]})
    assert resp.status_code == 200, resp.text
    assert resp.json()["deleted"] == 4
    resp = await client.get("/api/v1/knowledge", headers=auth)
    assert not [e for e in resp.json() if e["vulnerability_name"].startswith("批量-")]


async def test_word_import_knowledge_backfill(client: AsyncClient, auth: dict):
    """Word 导入确认入库：描述/修复建议为空时自动套用知识库模板。"""
    # 准备 vul_type=15 的模板
    resp = await client.post(
        "/api/v1/knowledge", headers=auth,
        json={"vulnerability_name": "存储型XSS", "vul_type": 15, "severity_level": 20,
              "description_html": "<p>回填标准描述</p>",
              "harm_html": "<p>回填危害说明</p>", "solution_html": "<p>回填修复建议</p>"},
    )
    assert resp.status_code == 200, resp.text

    # 上传官方模板样例并等待解析
    resp = await client.get("/api/v1/imports/template", headers=auth)
    resp = await client.post(
        "/api/v1/imports", headers=auth,
        files={"file": ("知识库回填样例.docx", BytesIO(resp.content),
                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
    )
    batch_id = resp.json()["id"]
    detail = await _wait_batch(client, auth, batch_id)
    rec = detail["records"][0]

    # 清空描述/修复建议并改为模板类型，确认入库触发回填
    resp = await client.put(
        f"/api/v1/imports/records/{rec['id']}", headers=auth,
        json={"title": "知识库回填漏洞", "vul_type": 15,
              "description_html": "", "solution_html": ""},
    )
    assert resp.status_code == 200, resp.text
    resp = await client.post(
        f"/api/v1/imports/{batch_id}/confirm", headers=auth,
        json={"record_ids": [rec["id"]]},
    )
    assert resp.status_code == 200, resp.text

    resp = await client.get("/api/v1/vulns", headers=auth, params={"search": "知识库回填漏洞"})
    vul = resp.json()["items"][0]
    assert "回填标准描述" in vul["description_html"]
    assert "危害说明" in vul["description_html"]
    assert "回填危害说明" in vul["description_html"]
    assert vul["solution_html"] == "<p>回填修复建议</p>"


async def test_vuln_list_sorting(client: AsyncClient, auth: dict):
    """漏洞列表按 level 升序排序结果非降序；sort 非法字段回退默认排序不报错。"""
    # 造三条不同等级的漏洞
    for lv in (40, 10, 30):
        resp = await client.post(
            "/api/v1/vulns", headers=auth,
            json={"title": f"排序用例漏洞-{lv}", "level": lv, "vul_type": 30},
        )
        assert resp.status_code == 200, resp.text

    resp = await client.get(
        "/api/v1/vulns", headers=auth, params={"sort": "level", "order": "asc", "size": 100},
    )
    assert resp.status_code == 200, resp.text
    levels = [v["level"] for v in resp.json()["items"]]
    assert levels == sorted(levels), levels

    # 降序
    resp = await client.get(
        "/api/v1/vulns", headers=auth, params={"sort": "level", "order": "desc", "size": 100},
    )
    levels = [v["level"] for v in resp.json()["items"]]
    assert levels == sorted(levels, reverse=True), levels

    # 非法排序字段回退默认排序（不报错）
    resp = await client.get(
        "/api/v1/vulns", headers=auth, params={"sort": "drop table", "order": "asc"},
    )
    assert resp.status_code == 200, resp.text


async def test_knowledge_default_sorting(client: AsyncClient, auth: dict):
    """知识库列表默认按 severity_level 升序为主、vul_type 升序为次。"""
    entries = [
        {"vulnerability_name": "排序模板A", "vul_type": 40, "severity_level": 30},
        {"vulnerability_name": "排序模板B", "vul_type": 20, "severity_level": 30},
        {"vulnerability_name": "排序模板C", "vul_type": 60, "severity_level": 10},
    ]
    for e in entries:
        resp = await client.post("/api/v1/knowledge", headers=auth, json=e)
        assert resp.status_code == 200, resp.text

    resp = await client.get("/api/v1/knowledge", headers=auth)
    assert resp.status_code == 200, resp.text
    rows = resp.json()
    # 主关键字 severity_level 升序，同级时 vul_type 升序
    keys = [(r["severity_level"], r["vul_type"]) for r in rows]
    assert keys == sorted(keys), keys


async def test_plan_complete_no_vuln_flow(client: AsyncClient, auth: dict):
    """无漏洞闭环：无漏洞完结 → 测试通过 + 无漏洞报告 → 重复确认拒绝 → 补录漏洞自动重开。"""
    # meta 字典包含新增的「测试通过」状态
    meta = (await client.get("/api/v1/meta", headers=auth)).json()
    assert meta["testing_plan_status"]["70"] == "测试通过"

    # 初测中且无漏洞的计划
    resp = await client.post(
        "/api/v1/testing-plans", headers=auth,
        json={"system_name": "无漏洞闭环系统", "test_type": "渗透测试",
              "receive_time": "2026-08-01", "status": 20},
    )
    assert resp.status_code == 200, resp.text
    plan_id = resp.json()["id"]

    # 确认无漏洞完结：状态流转、初测完成打点、结论记录、无漏洞报告生成
    resp = await client.post(
        f"/api/v1/testing-plans/{plan_id}/complete-no-vuln", headers=auth,
        json={"conclusion": "覆盖 OWASP Top 10 主要攻击面，未发现安全漏洞",
              "generate_report": True, "title": ""},
    )
    assert resp.status_code == 200, resp.text
    plan = resp.json()
    assert plan["status"] == 70
    assert plan["no_vul_conclusion"] == "覆盖 OWASP Top 10 主要攻击面，未发现安全漏洞"
    assert plan["first_test_done_time"]
    assert len(plan["reports"]) == 1
    report_brief = plan["reports"][0]
    assert "无漏洞闭环系统" in report_brief["title"]
    assert "渗透测试报告（无漏洞）" in report_brief["title"]
    # 无漏洞报告按初测报告口径计入计划实际人天（接收日期至确认当天）
    assert plan["actual_mandays"] >= 1

    # 报告单章节「测试结论」，无漏洞关联，结论含安全测试通过文案与补充说明
    resp = await client.get(f"/api/v1/reports/{report_brief['id']}", headers=auth)
    assert resp.status_code == 200, resp.text
    detail = resp.json()
    assert detail["testing_plan_id"] == plan_id
    assert len(detail["sections"]) == 1
    section = detail["sections"][0]
    assert section["title"] == "测试结论"
    assert section["vul_id"] is None
    assert "未发现" in section["content_html"]
    assert "安全测试通过" in section["content_html"]
    assert "OWASP" in section["content_html"]

    # 重复确认被拒绝
    resp = await client.post(f"/api/v1/testing-plans/{plan_id}/complete-no-vuln", headers=auth, json={})
    assert resp.status_code == 400

    # 补录漏洞后计划自动重开为「初测中」（关联需先认领）
    resp = await client.post(f"/api/v1/testing-plans/{plan_id}/claim", headers=auth)
    assert resp.status_code == 200, resp.text
    resp = await client.post(
        "/api/v1/vulns", headers=auth, json={"title": "无漏洞闭环补录漏洞", "level": 30},
    )
    assert resp.status_code == 200, resp.text
    vul_id = resp.json()["id"]
    resp = await client.post(
        f"/api/v1/testing-plans/{plan_id}/attach-vulns", headers=auth, json={"vul_ids": [vul_id]},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == 20
    # 重开后不可再确认无漏洞（存在关联漏洞），无漏洞测试结论保留以便追溯
    resp = await client.post(f"/api/v1/testing-plans/{plan_id}/complete-no-vuln", headers=auth, json={})
    assert resp.status_code == 400
    plan = (await client.get(f"/api/v1/testing-plans/{plan_id}", headers=auth)).json()
    assert plan["no_vul_conclusion"] == "覆盖 OWASP Top 10 主要攻击面，未发现安全漏洞"


async def test_plan_complete_no_vuln_requires_no_vulns(client: AsyncClient, auth: dict):
    """存在关联漏洞的计划不能确认无漏洞；直接创建漏洞到已通过计划同样触发重开。"""
    resp = await client.post(
        "/api/v1/testing-plans", headers=auth,
        json={"system_name": "有漏洞系统", "receive_time": "2026-08-01", "status": 20},
    )
    assert resp.status_code == 200, resp.text
    plan_id = resp.json()["id"]
    # 录入/关联漏洞需先认领计划
    resp = await client.post(f"/api/v1/testing-plans/{plan_id}/claim", headers=auth)
    assert resp.status_code == 200, resp.text
    resp = await client.post(
        "/api/v1/vulns", headers=auth,
        json={"title": "有漏洞系统-漏洞1", "level": 40, "testing_plan_id": plan_id},
    )
    assert resp.status_code == 200, resp.text
    vid = resp.json()["id"]

    # 有关联漏洞时拒绝无漏洞完结
    resp = await client.post(f"/api/v1/testing-plans/{plan_id}/complete-no-vuln", headers=auth, json={})
    assert resp.status_code == 400

    # 移除漏洞后不生成报告仅流转状态与记录结论
    resp = await client.delete(f"/api/v1/vulns/{vid}", headers=auth)
    assert resp.status_code == 200
    resp = await client.post(
        f"/api/v1/testing-plans/{plan_id}/complete-no-vuln", headers=auth,
        json={"conclusion": "仅完结不生成报告", "generate_report": False},
    )
    assert resp.status_code == 200, resp.text
    plan = resp.json()
    assert plan["status"] == 70
    assert plan["reports"] == []

    # 直接向已通过计划创建漏洞（不经 attach-vulns）同样自动重开
    resp = await client.post(
        "/api/v1/vulns", headers=auth,
        json={"title": "有漏洞系统-漏洞2", "level": 40, "testing_plan_id": plan_id},
    )
    assert resp.status_code == 200, resp.text
    plan = (await client.get(f"/api/v1/testing-plans/{plan_id}", headers=auth)).json()
    assert plan["status"] == 20


