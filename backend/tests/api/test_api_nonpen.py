"""API 集成测试：漏扫基线工单（`/nonpen-plans`）。

**由来（2026-09-22 契约检查整改）**：`NonpenPlanOut.asset_names` 此前**只有前端声明、后端从不返回**，
导致 `NonpenPlanWorkflowDrawer` 的「关联资产」块永不渲染（死代码）；同时这组接口此前**没有 API 级用例**
（仅被开放 API 的 PAT 用例间接触及）。本文件固化「资产名称在创建 / 列表 / 详情 / 更新 / 流转五类响应中
都可取到」，避免该字段再次丢失。
"""
import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _asset(client: AsyncClient, auth: dict, name: str) -> int:
    resp = await client.post("/api/v1/assets", headers=auth, json={"name": name})
    assert resp.status_code == 200, resp.text
    return resp.json()["id"]


async def test_nonpen_asset_names_in_all_responses(client: AsyncClient, auth: dict):
    """关联资产名称：顺序跟随 asset_ids，且在创建/列表/详情/更新/流转响应中都返回。"""
    a1 = await _asset(client, auth, "漏扫资产甲")
    a2 = await _asset(client, auth, "漏扫资产乙")
    payload = {
        "system_name": "资产名回显系统", "department": "信息部",
        "receive_time": "2026-09-22", "test_items": ["baseline", "web"],
    }

    # 创建
    resp = await client.post("/api/v1/nonpen-plans", headers=auth, json={**payload, "asset_ids": [a1, a2]})
    assert resp.status_code == 200, resp.text
    created = resp.json()
    row_id = created["id"]
    assert created["asset_names"] == ["漏扫资产甲", "漏扫资产乙"]

    # 列表（按系统名精确检索，避免受库内其它数据影响）
    resp = await client.get(
        "/api/v1/nonpen-plans", headers=auth, params={"search": "资产名回显系统", "size": 100},
    )
    assert resp.status_code == 200, resp.text
    row = next(x for x in resp.json()["items"] if x["id"] == row_id)
    assert row["asset_names"] == ["漏扫资产甲", "漏扫资产乙"]

    # 详情：流程抽屉刷新走此接口（即本缺陷的现场）
    resp = await client.get(f"/api/v1/nonpen-plans/{row_id}", headers=auth)
    assert resp.status_code == 200, resp.text
    assert resp.json()["asset_names"] == ["漏扫资产甲", "漏扫资产乙"]

    # 更新：改为只关联乙 → 名称同步且顺序跟随 asset_ids
    resp = await client.put(
        f"/api/v1/nonpen-plans/{row_id}", headers=auth,
        json={**payload, "asset_ids": [a2], "test_items": ["baseline"]},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["asset_names"] == ["漏扫资产乙"]

    # 测试项流转：响应同样带 asset_names（抽屉内流转后无需重新拉详情）
    resp = await client.post(
        f"/api/v1/nonpen-plans/{row_id}/items/baseline/transition",
        headers=auth, json={"action": "start"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["asset_names"] == ["漏扫资产乙"]


async def test_nonpen_search_ticket_id_excludes_ghost_seq(client: AsyncClient, auth: dict):
    """漏扫基线工单搜索同口径：手工改号后残留的 ticket_seq 不得被自动编号口径误命中。

    与 `test_api_plans.py::test_plan_search_ticket_id_excludes_ghost_seq` 对称 —— 两表共享
    工单ID序列，但关键词搜索是两份独立实现（`plan_query.nonpen_search_condition`）。
    """
    payload = {"system_name": "漏扫幽灵序号系统", "department": "信息部",
               "receive_time": "2026-07-31", "test_items": ["baseline"]}
    created: list[int] = []

    resp = await client.post("/api/v1/nonpen-plans", headers=auth, json=payload)
    assert resp.status_code == 200, resp.text
    ghost = resp.json()
    created.append(ghost["id"])
    ghost_ticket = ghost["ticket_id"]  # 自动编号（此刻尚无任何记录显示它）
    assert ghost_ticket.startswith("20260731-")

    # 手工改号为另一个日期的编号：底层 ticket_seq 残留成「幽灵序号」
    resp = await client.put(f"/api/v1/nonpen-plans/{ghost['id']}", headers=auth,
                            json={**payload, "ticket_id_manual": "20991231-98"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["ticket_id"] == "20991231-98"

    # 另一条记录接管该显示编号
    resp = await client.post("/api/v1/nonpen-plans", headers=auth,
                             json={**payload, "ticket_id_manual": ghost_ticket})
    assert resp.status_code == 200, resp.text
    takeover_id = resp.json()["id"]
    created.append(takeover_id)

    try:
        resp = await client.get("/api/v1/nonpen-plans", headers=auth,
                                params={"search": ghost_ticket, "size": 100})
        assert resp.status_code == 200, resp.text
        ids = [x["id"] for x in resp.json()["items"]]
        assert ghost["id"] not in ids, f"幽灵序号记录被误命中：{ids}"
        assert takeover_id in ids, f"接管记录未被命中：{ids}"
    finally:
        for plan_id in created:
            await client.delete(f"/api/v1/nonpen-plans/{plan_id}", headers=auth)

