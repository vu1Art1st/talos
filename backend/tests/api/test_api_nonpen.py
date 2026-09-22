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
