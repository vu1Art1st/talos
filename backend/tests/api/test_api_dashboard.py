"""API 集成测试：仪表盘与统计。

仪表盘与统计：总览、按部门、按资产分组、事件筛选（时间范围）。

原 tests/test_api.py（4626 行单体）按领域拆分而来：用例源码逐字未改，
仅按领域重新归位；共享夹具见 tests/conftest.py，共享 helper 见 tests/api/_helpers.py。
"""
import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_dashboard(client: AsyncClient, auth: dict):
    """总览统计：本次新建的漏洞必须实时反映在 total_vulns 与分布/趋势中。

    **自建数据**（2026-09-22 拆分时整改）：原实现断言 `total_vulns >= 2`，依赖同文件
    靠前用例先造出漏洞，本模块单独运行或与其他模块并行执行时不再成立。现自行建 2 条漏洞，
    断言口径不变（仍是「新建数据必须被统计到」），并保证模块可独立运行。
    """
    asset = (await client.post(
        "/api/v1/assets", headers=auth, json={"name": "看板总览资产"},
    )).json()
    created: list[int] = []
    try:
        for i, level in enumerate((20, 30), start=1):
            resp = await client.post(
                "/api/v1/vulns", headers=auth,
                json={"title": f"看板总览漏洞{i}", "level": level, "asset_ids": [asset["id"]]},
            )
            assert resp.status_code == 200, resp.text
            created.append(resp.json()["id"])

        resp = await client.get("/api/v1/dashboard/stats", headers=auth)
        assert resp.status_code == 200
        stats = resp.json()
        assert stats["total_vulns"] >= 2
        assert "by_level" in stats and "trend" in stats
        assert len(stats["trend"]) == 12
    finally:
        for vul_id in created:
            await client.delete(f"/api/v1/vulns/{vul_id}", headers=auth)
        await client.delete(f"/api/v1/assets/{asset['id']}", headers=auth)

async def test_vuln_stats_by_asset(client: AsyncClient, auth: dict):
    """/vulns/stats 按资产分组：by_asset 存在、计数正确、部门筛选联动。"""
    a1 = (await client.post(
        "/api/v1/assets", headers=auth,
        json={"name": "统计资产甲", "department": "统计部门A"},
    )).json()
    a2 = (await client.post(
        "/api/v1/assets", headers=auth,
        json={"name": "统计资产乙", "department": "统计部门B"},
    )).json()
    v1 = v2 = None
    try:
        v1 = (await client.post(
            "/api/v1/vulns", headers=auth,
            json={"title": "统计漏洞一", "level": 20, "asset_ids": [a1["id"], a2["id"]]},
        )).json()
        v2 = (await client.post(
            "/api/v1/vulns", headers=auth,
            json={"title": "统计漏洞二", "level": 30, "asset_ids": [a2["id"]]},
        )).json()

        # 全量统计：同一漏洞关联多资产时按关联关系在各资产分组重复计入
        # （session 级共享数据库，不依赖全局 total，只校验本次创建的资产）
        stats = (await client.get("/api/v1/vulns/stats", headers=auth)).json()
        assert "by_asset" in stats
        asset_count = {r["asset_id"]: r["count"] for r in stats["by_asset"]}
        assert asset_count[a1["id"]] == 1
        assert asset_count[a2["id"]] == 2
        # departments：资产部门去重列表（含全部资产部门，供组合工具选部门）
        assert "departments" in stats
        assert {"统计部门A", "统计部门B"} <= set(stats["departments"])

        # 部门筛选联动：该部门漏洞计入（跨部门关联的乙也会带出，前端以资产列表为选项源过滤）
        dept_stats = (await client.get(
            "/api/v1/vulns/stats", headers=auth, params={"department": "统计部门A"},
        )).json()
        dept_asset_count = {r["asset_id"]: r["count"] for r in dept_stats["by_asset"]}
        assert dept_asset_count[a1["id"]] == 1
    finally:
        for v in (v1, v2):
            if v:
                await client.delete(f"/api/v1/vulns/{v['id']}", headers=auth)
        await client.delete(f"/api/v1/assets/{a2['id']}", headers=auth)
        await client.delete(f"/api/v1/assets/{a1['id']}", headers=auth)

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

    # 单独录入的漏洞（未关联工单）：来源可选，且关联工单的漏洞来源恒为工单（source 强制 0）
    resp = await client.post("/api/v1/assets", headers=auth, json={"name": "态势来源资产"})
    src_asset_id = resp.json()["id"]
    resp = await client.post(
        "/api/v1/vulns", headers=auth,
        json={"title": "态势来源筛选漏洞", "level": 30, "source": 20, "asset_ids": [src_asset_id]},
    )
    assert resp.status_code == 200, resp.text

    # 来源筛选：命中单独录入且来源=20（春耕行动）的漏洞
    # （全库口径用 >=1：其它模块也会造 source=20 的数据，2026-09-22 拆分时改为与库内其它数据无关的断言）
    stats = (await client.get(
        "/api/v1/dashboard/stats", headers=auth,
        params={"source": 20},
    )).json()
    assert stats["total_vulns"] >= 1
    # 关键不变量（部门内口径，与全库其它数据无关）：本部门 2 条漏洞关联工单、来源被强制为 0，不被命中
    stats = (await client.get(
        "/api/v1/dashboard/stats", headers=auth,
        params={"department": dept, "source": 20},
    )).json()
    assert stats["total_vulns"] == 0

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
