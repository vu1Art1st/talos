"""API 集成测试：复测链路。

复测链路：工单级复测完成判定、无更新拦截、轮次记录与回退、复测记录同步到漏洞、漏
洞状态守卫、二轮复测必须新增记录。

原 tests/test_api.py（4626 行单体）按领域拆分而来：用例源码逐字未改，
仅按领域重新归位；共享夹具见 tests/conftest.py，共享 helper 见 tests/api/_helpers.py。
"""
import re
import pytest
from httpx import AsyncClient

from _helpers import _get_plan

pytestmark = pytest.mark.asyncio(loop_scope="session")


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
        "stat_critical", "stat_high", "stat_medium", "stat_low", "target_urls", "detail",
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
    """安全态势部门维度：提测次数 / 发现漏洞（含手填补充） / 修复率 / 占用人天（实际人天求和）。

    **归属本模块**（2026-09-22 拆分时从原 test_api.py 的看板段移来）：断言使用的「轮次部门」
    数据由本模块前一个用例 `test_retest_round_tracking` 造出 —— 属**同模块内的顺序依赖**，
    请勿单独把它挪到别的模块（挪走即 StopIteration）。
    """
    # 无关联漏洞的计划：发现数取手填统计，修复率为空；占用人天取实际人天
    resp = await client.post(
        "/api/v1/testing-plans", headers=auth,
        json={"system_name": "看板系统", "department": "看板部门",
              "stat_high": 2, "stat_low": 1, "actual_mandays": 3.5},
    )
    assert resp.status_code == 200, resp.text

    stats = (await client.get("/api/v1/dashboard/stats", headers=auth)).json()
    assert "by_department" in stats
    dept = next(d for d in stats["by_department"] if d["department"] == "看板部门")
    assert dept["plans"] == 1
    assert dept["vulns"] == 3
    assert dept["fixed"] == 0
    assert dept["fix_rate"] is None
    assert dept["mandays"] == 3.5
    # 高危及以上取手填严重(0)+高危(2)；手填统计无状态概念，全部计为未闭环
    assert dept["high"] == 2
    assert dept["open"] == 3

    # 有关联漏洞的计划（test_retest_round_tracking：高危A 已修复 + 中危B 已忽略）
    dept2 = next(d for d in stats["by_department"] if d["department"] == "轮次部门")
    assert dept2["plans"] == 1
    assert dept2["vulns"] == 2
    assert dept2["fixed"] == 1
    assert dept2["fix_rate"] == 50.0
    assert isinstance(dept2["mandays"], (int, float))
    # 高危及以上仅高危A；未闭环 = 2 − 已修复1 − 已忽略1 = 0
    assert dept2["high"] == 1
    assert dept2["open"] == 0

async def test_delete_retest_report_rolls_back_round(client: AsyncClient, auth: dict):
    """删除新发起的复测记录后复测轮数正确回退：删除复测报告移除对应轮次；
    若删除的是 force 发起的新轮，上一轮恢复进行中状态，保持轮次状态与计划状态一致。"""
    resp = await client.post(
        "/api/v1/testing-plans", headers=auth,
        json={"system_name": "轮次回退系统", "department": "轮次回退部门"},
    )
    assert resp.status_code == 200, resp.text
    plan_id = resp.json()["id"]
    await client.post(f"/api/v1/testing-plans/{plan_id}/claim", headers=auth)
    resp = await client.post("/api/v1/assets", headers=auth, json={"name": "轮次回退资产"})
    asset_id = resp.json()["id"]
    resp = await client.post(
        "/api/v1/vulns/batch", headers=auth,
        json={"asset_ids": [asset_id], "vulns": [
            {"title": "回退漏洞A", "level": 20, "testing_plan_id": plan_id},
        ]},
    )
    vul_a = resp.json()[0]["id"]

    # 生成初测报告 → 漏洞进入修复中，计划进入初测完成
    resp = await client.post(
        "/api/v1/reports/from-vulns", headers=auth,
        json={"title": "轮次回退报告", "vul_ids": [vul_a], "testing_plan_id": plan_id},
    )
    assert resp.status_code == 200, resp.text
    src_report = resp.json()["id"]

    # 发起复测 → 生成复测报告 R1、记录第 1 轮
    resp = await client.post(f"/api/v1/reports/{src_report}/retest", headers=auth)
    assert resp.status_code == 200, resp.text
    r1_id = resp.json()["id"]
    plan = await _get_plan(client, auth, plan_id)
    assert plan["retest_round_count"] == 1

    # 删除新发起的复测报告 R1 → 对应轮次回退，复测轮数归零，仅剩初测报告
    resp = await client.delete(f"/api/v1/reports/{r1_id}", headers=auth)
    assert resp.status_code == 200, resp.text
    plan = await _get_plan(client, auth, plan_id)
    assert plan["retest_round_count"] == 0
    assert len(plan["reports"]) == 1

    # 再次发起复测 → 重新开第 1 轮（进行中）
    resp = await client.post(f"/api/v1/reports/{src_report}/retest", headers=auth)
    assert resp.status_code == 200, resp.text
    plan = await _get_plan(client, auth, plan_id)
    assert plan["retest_round_count"] == 1
    assert plan["retest_rounds"][0]["done_time"] is None

    # 再次发起复测（漏洞已处于复测中）→ force 结束第 1 轮并开第 2 轮
    resp = await client.post(f"/api/v1/reports/{src_report}/retest", headers=auth)
    assert resp.status_code == 200, resp.text
    r3_id = resp.json()["id"]
    plan = await _get_plan(client, auth, plan_id)
    assert plan["retest_round_count"] == 2
    assert plan["retest_rounds"][0]["done_time"] is not None
    assert plan["retest_rounds"][1]["done_time"] is None

    # 删除最新复测报告 R3 → 轮数回退为 1，且上一轮恢复进行中
    resp = await client.delete(f"/api/v1/reports/{r3_id}", headers=auth)
    assert resp.status_code == 200, resp.text
    plan = await _get_plan(client, auth, plan_id)
    assert plan["retest_round_count"] == 1
    assert plan["retest_rounds"][0]["done_time"] is None

    # 删除初测报告不影响轮次（非复测报告不关联任何轮次）
    resp = await client.delete(f"/api/v1/reports/{src_report}", headers=auth)
    assert resp.status_code == 200, resp.text
    plan = await _get_plan(client, auth, plan_id)
    assert plan["retest_round_count"] == 1
    assert plan["retest_rounds"][0]["done_time"] is None

async def test_retest_record_sync_to_vul(client: AsyncClient, auth: dict):
    """复测记录增/改/删同步聚合到 Vul.retest_html（详情页/报告读取口径）。"""
    resp = await client.post(
        "/api/v1/vulns", headers=auth, json={"title": "复测同步漏洞", "level": 20},
    )
    vul_id = resp.json()["id"]

    # 新增一条记录：retest_html 同步为记录内容（标题格式「复测记录yymmdd」）
    resp = await client.post(
        f"/api/v1/vulns/{vul_id}/retests", headers=auth,
        json={"content_html": "<p>第一次复测仍存在</p>", "content_json": None},
    )
    assert resp.status_code == 200, resp.text
    rec1_id = resp.json()["id"]
    vul = (await client.get(f"/api/v1/vulns/{vul_id}", headers=auth)).json()
    assert re.search(r"复测记录\d{6}：", vul["retest_html"])
    assert "第一次复测仍存在" in vul["retest_html"]

    # 第二条记录：同日新增，标题追加 -1 后缀
    resp = await client.post(
        f"/api/v1/vulns/{vul_id}/retests", headers=auth,
        json={"content_html": "<p>第二次复测已修复</p>", "content_json": None},
    )
    rec2_id = resp.json()["id"]
    vul = (await client.get(f"/api/v1/vulns/{vul_id}", headers=auth)).json()
    assert re.search(r"复测记录\d{6}：", vul["retest_html"])
    assert re.search(r"复测记录\d{6}-1：", vul["retest_html"])
    assert "第一次复测仍存在" in vul["retest_html"]
    assert "第二次复测已修复" in vul["retest_html"]

    # 自定义标题优先于自动日期标题（手动编辑复测标题对应实际复测时间）
    resp = await client.put(
        f"/api/v1/vulns/{vul_id}/retests/{rec2_id}", headers=auth,
        json={"title": "复测记录250815", "content_html": "<p>第二次复测已修复</p>", "content_json": None},
    )
    assert resp.status_code == 200, resp.text
    vul = (await client.get(f"/api/v1/vulns/{vul_id}", headers=auth)).json()
    assert "<strong>复测记录250815：</strong>" in vul["retest_html"]
    assert "第二次复测已修复" in vul["retest_html"]

    # 清空自定义标题后回退为自动日期标题（同日追加 -1 后缀）
    resp = await client.put(
        f"/api/v1/vulns/{vul_id}/retests/{rec2_id}", headers=auth,
        json={"title": None, "content_html": "<p>第二次复测已修复</p>", "content_json": None},
    )
    assert resp.status_code == 200, resp.text
    vul = (await client.get(f"/api/v1/vulns/{vul_id}", headers=auth)).json()
    assert re.search(r"复测记录\d{6}-1：", vul["retest_html"])
    assert "<strong>复测记录250815：</strong>" not in vul["retest_html"]

    # 更新记录：聚合内容跟随变化
    resp = await client.put(
        f"/api/v1/vulns/{vul_id}/retests/{rec2_id}", headers=auth,
        json={"content_html": "<p>第二次复测部分修复</p>", "content_json": None},
    )
    assert resp.status_code == 200, resp.text
    vul = (await client.get(f"/api/v1/vulns/{vul_id}", headers=auth)).json()
    assert "第二次复测部分修复" in vul["retest_html"]
    assert "第二次复测已修复" not in vul["retest_html"]

    # 删除一条：回到单条内容（标题不带 -N 后缀）
    resp = await client.delete(f"/api/v1/vulns/{vul_id}/retests/{rec2_id}", headers=auth)
    assert resp.status_code == 200
    vul = (await client.get(f"/api/v1/vulns/{vul_id}", headers=auth)).json()
    assert re.search(r"复测记录\d{6}：", vul["retest_html"])
    assert not re.search(r"复测记录\d{6}-\d：", vul["retest_html"])
    assert "第一次复测仍存在" in vul["retest_html"]

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

async def test_second_round_retest_requires_new_record(client: AsyncClient, auth: dict):
    """二轮复测不得误用首轮历史复测记录放行：本轮无新记录时禁止切换为已修复/复测未通过。"""
    resp = await client.post("/api/v1/vulns", headers=auth, json={"title": "二轮复测守卫漏洞", "level": 20})
    vul_id = resp.json()["id"]

    # 首轮：50 → 55 → 新增复测记录并闭环为已修复
    for status in (50, 55):
        resp = await client.post(f"/api/v1/vulns/{vul_id}/transition", headers=auth, json={"status": status})
        assert resp.status_code == 200, resp.text
    resp = await client.post(
        f"/api/v1/vulns/{vul_id}/retests", headers=auth,
        json={"content_html": "<p>首轮复测通过</p>", "status": 60},
    )
    assert resp.status_code == 200, resp.text

    # 二轮：已修复重新发起复测（FIXED→RETESTING），未新增任何记录
    resp = await client.post(f"/api/v1/vulns/{vul_id}/transition", headers=auth, json={"status": 55})
    assert resp.status_code == 200, resp.text
    vul = (await client.get(f"/api/v1/vulns/{vul_id}", headers=auth)).json()
    assert vul["status"] == 55
    assert vul["retest_html"]  # 首轮历史记录仍聚合在 retest_html 中（旧校验会误放行）

    # 本轮无新记录：直接切换为已修复 → 拒绝
    resp = await client.post(f"/api/v1/vulns/{vul_id}/transition", headers=auth, json={"status": 60})
    assert resp.status_code == 400

    # 本轮无新记录：复测未通过回修复中 → 拒绝
    resp = await client.post(f"/api/v1/vulns/{vul_id}/transition", headers=auth, json={"status": 50})
    assert resp.status_code == 400

    # 本轮无新记录：编辑页直接点选为已修复（set_status 路径）→ 拒绝
    resp = await client.patch(f"/api/v1/vulns/{vul_id}/fields", headers=auth, json={"status": 60})
    assert resp.status_code == 400

    # 本轮新增复测记录后再流转 → 放行
    resp = await client.post(
        f"/api/v1/vulns/{vul_id}/retests", headers=auth,
        json={"content_html": "<p>二轮复测通过</p>", "status": 60},
    )
    assert resp.status_code == 200, resp.text
    vul = (await client.get(f"/api/v1/vulns/{vul_id}", headers=auth)).json()
    assert vul["status"] == 60

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
