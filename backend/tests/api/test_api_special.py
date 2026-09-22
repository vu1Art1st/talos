"""API 集成测试：专项三域（远程检测 / 春耕行动 / 报告附件）。

专项三域：远程检测 / 春耕行动 / 报告附件（含上传白名单、附件下载与删除）。

原 tests/test_api.py（4626 行单体）按领域拆分而来：用例源码逐字未改，
仅按领域重新归位；共享夹具见 tests/conftest.py，共享 helper 见 tests/api/_helpers.py。
"""
from io import BytesIO
import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_special_modules_crud(client: AsyncClient, auth: dict):
    """三个专项模块：远程检测 / 测试计划 / 春耕行动 CRUD。"""
    # ---- 远程检测（2026-08-14 通报口径；2026-09-11 关联资产台账与漏洞库） ----
    # 关联资产：系统名称/部门由资产带出，另存资产归属
    resp = await client.post(
        "/api/v1/assets", headers=auth, json={"name": "门户系统", "department": "信息部"},
    )
    assert resp.status_code == 200, resp.text
    rt_asset_id = resp.json()["id"]

    resp = await client.post(
        "/api/v1/remote-testings", headers=auth,
        json={"system_name": "门户系统", "notice_time": "2026-01", "department": "信息部",
              "asset_belong": "省公司", "asset_id": rt_asset_id,
              "notified_unit": "省公司", "is_external": False,
              "new_vul": {"title": "SQL注入", "level": 20, "vul_type": 30, "source": 10},
              "appeal_status": "", "appeal_method": "",
              "appeal_file_name": "", "appeal_file_path": "", "appeal_file_size": 0},
    )
    assert resp.status_code == 200, resp.text
    rt = resp.json()
    rt_id = rt["id"]
    assert rt["system_name"] == "门户系统"
    assert rt["asset"]["id"] == rt_asset_id
    assert rt["asset_belong"] == "省公司"
    # 「新增漏洞」草稿随保存创建并关联，文本快照同步为漏洞口径
    assert rt["vuln"]["title"] == "SQL注入"
    assert rt["vuln"]["vul_type"] == 30
    assert rt["vuln_name"] == "SQL注入"
    assert rt["vuln_type"] == "30"
    rt_vul_id = rt["vuln"]["id"]

    # 申诉报告附件上传（返回文件元信息供表单绑定）
    resp = await client.post(
        "/api/v1/remote-testings/upload-appeal", headers=auth,
        files={"file": ("appeal.pdf", b"%PDF-1.4 test", "application/pdf")},
    )
    assert resp.status_code == 200, resp.text
    up = resp.json()
    assert up["name"] == "appeal.pdf"
    assert up["path"].startswith("uploads/remote_appeal/")
    assert up["size"] == len(b"%PDF-1.4 test")

    resp = await client.put(
        f"/api/v1/remote-testings/{rt_id}", headers=auth,
        json={"system_name": "门户系统", "notice_time": "2026-02", "department": "信息部",
              "asset_belong": "省公司", "asset_id": rt_asset_id,
              "notified_unit": "省公司", "is_external": True, "vuln_id": rt_vul_id,
              "appeal_status": "success", "appeal_method": "线下申诉",
              "appeal_file_name": up["name"], "appeal_file_path": up["path"],
              "appeal_file_size": up["size"]},
    )
    assert resp.status_code == 200
    assert resp.json()["appeal_status"] == "success"
    # 保留关联漏洞时文本快照继续由漏洞派生，不受前端是否有文本输入影响
    assert resp.json()["vuln_id"] == rt_vul_id
    assert resp.json()["vuln"]["id"] == rt_vul_id

    # 关联漏洞不存在时拒绝保存
    resp = await client.post(
        "/api/v1/remote-testings", headers=auth,
        json={"system_name": "非法关联系统", "vuln_id": 999999},
    )
    assert resp.status_code == 400

    # 申诉报告附件下载
    resp = await client.get(f"/api/v1/remote-testings/{rt_id}/appeal", headers=auth)
    assert resp.status_code == 200
    assert resp.content == b"%PDF-1.4 test"

    resp = await client.get("/api/v1/remote-testings", headers=auth, params={"search": "门户"})
    assert rt_id in [r["id"] for r in resp.json()["items"]]
    # 部门列为独立字段可检索；关联漏洞标题同样参与检索（列表「漏洞名称」点击查看详情）
    resp = await client.get("/api/v1/remote-testings", headers=auth, params={"search": "SQL注入"})
    hit = [r for r in resp.json()["items"] if r["id"] == rt_id]
    assert hit and hit[0]["vuln"]["title"] == "SQL注入"

    # ---- 测试计划 ----
    resp = await client.post(
        "/api/v1/testing-plans", headers=auth,
        json={"system_name": "计划系统", "test_type": "渗透测试", "department": "研发部",
              "receive_time": "2026-01-01", "first_test_done_time": "2026-01-05",
              "status": 20, "stat_critical": 1, "stat_high": 2, "stat_medium": 3,
              "stat_low": 4, "target_urls": ["https://plan.example.com"],
              "detail": "测试人员：张三"},
    )
    assert resp.status_code == 200, resp.text
    plan = resp.json()
    assert plan["stat_high"] == 2
    assert plan["target_urls"] == ["https://plan.example.com"]

    # 编辑：被测系统URL支持增删（替换）
    resp = await client.put(
        f"/api/v1/testing-plans/{plan['id']}", headers=auth,
        json={"system_name": "计划系统", "test_type": "渗透测试", "department": "研发部",
              "receive_time": "2026-01-01", "status": 20,
              "target_urls": ["https://a.example.com", "http://10.20.1.10:8080"]},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["target_urls"] == ["https://a.example.com", "http://10.20.1.10:8080"]

    # status 筛选
    resp = await client.get("/api/v1/testing-plans", headers=auth, params={"status": 20})
    assert plan["id"] in [p["id"] for p in resp.json()["items"]]
    resp = await client.get("/api/v1/testing-plans", headers=auth, params={"status": 50})
    assert plan["id"] not in [p["id"] for p in resp.json()["items"]]

    # meta 提供六档状态字典
    meta = (await client.get("/api/v1/meta", headers=auth)).json()
    assert meta["testing_plan_status"]["10"] == "未测试"
    assert meta["testing_plan_status"]["30"] == "初测完成"
    assert meta["testing_plan_status"]["40"] == "提请复测"
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
              "asset_reason": "备案归属本单位", "appeal_success": True,
              "est_score_deduction": 4, "score_deduction": 2.5,
              "doc_no": "公文〔2026〕1号", "vul_ids": [vul_id]},
    )
    assert resp.status_code == 200, resp.text
    sa = resp.json()
    assert sa["vul_ids"] == [vul_id]
    assert sa["vuls"][0]["title"] == "春耕漏洞"
    assert sa["asset_reason"] == "备案归属本单位"
    assert sa["est_score_deduction"] == 4
    assert sa["score_deduction"] == 2.5

    # 更新：清空漏洞关联
    resp = await client.put(
        f"/api/v1/spring-actions/{sa['id']}", headers=auth,
        json={"report_no": "RPT-2026-001", "system_name": "春耕系统",
              "asset_reason": "", "appeal_success": False,
              "est_score_deduction": 0, "score_deduction": 0,
              "doc_no": "", "vul_ids": []},
    )
    assert resp.status_code == 200
    assert resp.json()["vuls"] == []

    # 列表返回漏洞摘要
    resp = await client.get("/api/v1/spring-actions", headers=auth, params={"search": "RPT-2026"})
    assert len(resp.json()["items"]) == 1

    # ---- 原始报告上传导入 ----
    from docx import Document as _Docx

    # 非 docx 被拒绝
    resp = await client.post(
        "/api/v1/spring-actions/upload-report", headers=auth,
        files={"file": ("原始报告.txt", b"not a docx", "text/plain")},
    )
    assert resp.status_code == 400

    # 无漏洞表的 docx 也可上传留档，解析返回空草稿
    buf = BytesIO()
    _Docx().save(buf)
    buf.seek(0)
    resp = await client.post(
        "/api/v1/spring-actions/upload-report", headers=auth,
        files={"file": ("原始报告.docx", buf,
                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
    )
    assert resp.status_code == 200, resp.text
    upload = resp.json()
    assert upload["name"] == "原始报告.docx"
    assert upload["path"].startswith("uploads/spring_report/")
    assert upload["size"] > 0
    assert upload["vuls"] == []

    # 保存：附件绑定 + 漏洞草稿随保存创建并关联（来源固定为春耕行动）
    resp = await client.post(
        "/api/v1/spring-actions", headers=auth,
        json={"report_no": "SA-2026-009", "system_name": "春耕附件系统",
              "report_file_name": upload["name"], "report_file_path": upload["path"],
              "report_file_size": upload["size"],
              "new_vuls": [{"title": "报告导入漏洞", "level": 20,
                            "description_html": "<p>报告描述内容</p>"}]},
    )
    assert resp.status_code == 200, resp.text
    sa2 = resp.json()
    assert sa2["report_file_name"] == "原始报告.docx"
    assert [v["title"] for v in sa2["vuls"]] == ["报告导入漏洞"]
    # 漏洞摘要带所在层（网络层级列聚合展示依赖该字段）
    assert sa2["vuls"][0]["layer"] == 10

    # 附件下载
    resp = await client.get(f"/api/v1/spring-actions/{sa2['id']}/report", headers=auth)
    assert resp.status_code == 200

    # 收尾清理导入的漏洞（source=20 会污染后续 dashboard 来源筛选计数）
    imported_id = sa2["vuls"][0]["id"]
    resp = await client.post("/api/v1/vulns/batch-delete", headers=auth, json={"ids": [imported_id]})
    assert resp.status_code == 200

    # 清理远程检测「新增漏洞」创建的漏洞（避免污染历史漏洞库计数）
    resp = await client.post("/api/v1/vulns/batch-delete", headers=auth, json={"ids": [rt_vul_id]})
    assert resp.status_code == 200, resp.text

    # ---- 删除 ----
    for path in (f"/api/v1/remote-testings/{rt_id}",
                 f"/api/v1/testing-plans/{plan['id']}",
                 f"/api/v1/spring-actions/{sa['id']}",
                 f"/api/v1/spring-actions/{sa2['id']}"):
        resp = await client.delete(path, headers=auth)
        assert resp.status_code == 200
