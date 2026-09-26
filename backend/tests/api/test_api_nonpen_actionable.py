"""API 集成测试：漏扫基线「仅可进行」的 SQL 侧过滤（ROADMAP P0-4）。

背景：该筛选原先「取回最多 10000 条 → 应用层过滤 → 切片」，数据量增长后读取与内存线性放大。
现改为 `plan_query.nonpen_actionable_condition` 下推到 SQL。本文件锁定三件事：

1. **口径等价**：SQL 条件的结果集与 `NonpenPlan.actionable` 属性逐条一致（含各类测试项状态组合）；
2. **真分页**：`total` 是过滤后的全量计数，`page/size` 由数据库切片；
3. **站内 / 开放 API 同口径**，且路由层不再出现全量读取（源码守卫）。
"""
from pathlib import Path

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio(loop_scope="session")

_DEPT = "仅可进行专用部门"


async def _create(client: AsyncClient, auth: dict, name: str, items: list[str]) -> int:
    resp = await client.post(
        "/api/v1/nonpen-plans", headers=auth,
        json={
            "system_name": name, "department": _DEPT,
            "receive_time": "2026-09-26", "test_items": items,
        },
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["id"]


async def _transition(client: AsyncClient, auth: dict, plan_id: int, key: str, action: str) -> dict:
    resp = await client.post(
        f"/api/v1/nonpen-plans/{plan_id}/items/{key}/transition",
        headers=auth, json={"action": action},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _set_ignored(client: AsyncClient, auth: dict, plan_id: int, key: str) -> dict:
    """忽略测试项走专用端点（transition 的 action 白名单不含 ignore）。"""
    resp = await client.post(
        f"/api/v1/nonpen-plans/{plan_id}/items/{key}/ignore",
        headers=auth, json={"ignored": True},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _list(client: AsyncClient, auth: dict, **params) -> dict:
    resp = await client.get(
        "/api/v1/nonpen-plans", headers=auth, params={"search": _DEPT, **params},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


@pytest.fixture
async def actionable_cases(client: AsyncClient, auth: dict) -> dict[str, int]:
    """构造覆盖全部测试项状态的 6 条工单，返回 {用例名: id}。"""
    cases: dict[str, int] = {}
    cases["not_started"] = await _create(client, auth, "可进行-未开始", ["baseline"])
    cases["testing"] = await _create(client, auth, "可进行-初测中", ["baseline"])
    await _transition(client, auth, cases["testing"], "baseline", "start")
    cases["retesting"] = await _create(client, auth, "可进行-复测中", ["baseline"])
    for action in ("start", "done", "start_retest"):
        await _transition(client, auth, cases["retesting"], "baseline", action)
    cases["wait_retest"] = await _create(client, auth, "不可进行-初测完成", ["baseline"])
    for action in ("start", "done"):
        await _transition(client, auth, cases["wait_retest"], "baseline", action)
    cases["ignored"] = await _create(client, auth, "不可进行-已忽略", ["baseline"])
    await _set_ignored(client, auth, cases["ignored"], "baseline")
    cases["retest_done"] = await _create(client, auth, "不可进行-复测完成", ["baseline"])
    for action in ("start", "done", "start_retest", "pass"):
        await _transition(client, auth, cases["retest_done"], "baseline", action)

    yield cases
    for plan_id in cases.values():
        await client.delete(f"/api/v1/nonpen-plans/{plan_id}", headers=auth)


async def test_actionable_filter_matches_python_property(actionable_cases, client, auth):
    """SQL 侧过滤结果必须与 Python `actionable` 属性逐条一致（含已忽略 / 初测完成等负例）。"""
    all_rows = (await _list(client, auth, size=100))["items"]
    by_id = {row["id"]: row for row in all_rows}
    for name, plan_id in actionable_cases.items():
        assert plan_id in by_id, f"用例 {name} 未出现在检索范围内"

    expected = sorted(pid for pid, row in by_id.items() if row["actionable"])
    assert set(actionable_cases.values()) - set(expected) == {
        actionable_cases["wait_retest"],
        actionable_cases["ignored"],
        actionable_cases["retest_done"],
    }

    payload = await _list(client, auth, actionable=True, size=100)
    assert sorted(row["id"] for row in payload["items"]) == expected
    # 过滤后的每一行本身也必须为 actionable（不得出现 SQL 与属性口径漂移）
    assert all(row["actionable"] for row in payload["items"])


async def test_actionable_filter_paginates_in_sql(actionable_cases, client, auth):
    """真分页：total 为过滤后全量计数，page/size 由数据库切片（不再全量读取）。"""
    payload = await _list(client, auth, actionable=True, size=2, page=1)
    assert payload["total"] == 3
    assert len(payload["items"]) == 2
    second = await _list(client, auth, actionable=True, size=2, page=2)
    assert second["total"] == 3
    assert len(second["items"]) == 1
    # 两页不重叠
    first_ids = {row["id"] for row in payload["items"]}
    second_ids = {row["id"] for row in second["items"]}
    assert not (first_ids & second_ids)


async def test_actionable_filter_open_api_same_scope(actionable_cases, client, auth):
    """开放 API 与站内同口径（同一实现函数），P0-4 后同样走 SQL 侧过滤。"""
    resp = await client.post(
        "/api/v1/pats", headers=auth, json={"name": "漏扫可进行令牌", "expire_days": 7},
    )
    pat = {"Authorization": f"Bearer {resp.json()['token']}"}
    resp = await client.get(
        "/api/v1/open/nonpen-plans", headers=pat,
        params={"search": _DEPT, "actionable": True, "size": 100},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    internal = await _list(client, auth, actionable=True, size=100)
    assert {row["id"] for row in body["items"]} == {row["id"] for row in internal["items"]}
    assert body["total"] == internal["total"]


async def test_nonpen_routes_do_not_fetch_all_rows():
    """源码守卫：站内与开放 API 的漏扫列表不得再出现「取回 10000 条」的全量读取。"""
    root = Path(__file__).resolve().parent.parent.parent / "app" / "api" / "v1"
    for name in ("nonpen.py", "open_plans.py"):
        text = (root / name).read_text(encoding="utf-8")
        assert "10_000" not in text, f"{name} 仍在全量读取后再应用层过滤"
        assert "actionable" in text
        assert "nonpen_actionable_condition" in text, f"{name} 未复用统一条件构造"
