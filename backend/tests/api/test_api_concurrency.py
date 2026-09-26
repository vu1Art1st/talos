"""API 集成测试：并发写入一致性（ROADMAP P0-2）。

覆盖三条真实竞态路径，全部用 `asyncio.gather` 让请求真正并发（各自独立的数据库会话/连接）：

1. 同日并发创建工单：序号由 `ticket_seq_counters` 原子分配，不得出现重复工单ID；
   手填同一工单ID时由数据库唯一索引兜底，冲突方得到 4xx 而非 500。
2. 双端同时保存报告：`SELECT ... FOR UPDATE` + revision 比对，恰好一个成功、一个 409，
   不出现「后提交静默覆盖先提交」。
3. 同批次并发确认导入：条件状态迁移抢占，只有一次真正入库，重复调用幂等返回，
   不产生重复章节 / 漏洞 / 报告。
"""
import asyncio
import json

import pytest
from httpx import AsyncClient

from _helpers import _upload_report_batch

pytestmark = pytest.mark.asyncio(loop_scope="session")


def _rule(field: str, op: str, value) -> dict:
    return {"kind": "rule", "field": field, "op": op, "value": value, "not": False}


async def test_concurrent_plan_create_allocates_unique_ticket_ids(client: AsyncClient, auth: dict):
    """同日并发创建 4 个工单：工单ID 必须两两不同（序号分配原子且单调）。"""
    from app.core.timeutil import now as tznow

    dept = "并发创建专用部门"
    receive_time = tznow().date().isoformat()

    async def create(idx: int):
        return await client.post(
            "/api/v1/testing-plans", headers=auth,
            json={
                "system_name": f"并发创建系统-{idx}", "test_type": "渗透测试",
                "department": dept, "receive_time": receive_time,
            },
        )

    responses = await asyncio.gather(*[create(i) for i in range(4)])
    assert [r.status_code for r in responses] == [200] * 4, [r.text for r in responses]
    bodies = [r.json() for r in responses]
    ticket_ids = [b["ticket_id"] for b in bodies]
    try:
        assert len(set(ticket_ids)) == 4, f"并发创建产生重复工单ID：{ticket_ids}"
        assert all(t.startswith(receive_time.replace("-", "")) for t in ticket_ids)
        # 序号互不相同且落在 [1, 4]（同日序列共享，无空洞则 4 个连续值）
        seqs = sorted(int(t.split("-")[1]) for t in ticket_ids)
        assert seqs == list(range(seqs[0], seqs[0] + 4))
    finally:
        for b in bodies:
            await client.delete(f"/api/v1/testing-plans/{b['id']}", headers=auth)


async def test_concurrent_manual_ticket_id_conflicts_are_4xx(client: AsyncClient, auth: dict):
    """并发提交同一手填工单ID：恰好一个成功，其余明确 4xx（唯一索引兜底，不落 500）。"""
    manual = "20991231-7"
    dept = "并发手填编号部门"
    filters = json.dumps({"logic": "and", "children": [
        _rule("department", "eq", dept),
    ]})

    async def create(idx: int):
        return await client.post(
            "/api/v1/testing-plans", headers=auth,
            json={
                "system_name": f"并发手填系统-{idx}", "department": dept,
                "ticket_id_manual": manual,
            },
        )

    responses = await asyncio.gather(*[create(i) for i in range(3)])
    codes = sorted(r.status_code for r in responses)
    try:
        assert codes[0] == 200, [r.text for r in responses]
        assert all(400 <= c < 500 for c in codes[1:]), codes
        # 库里只应留下一条占用该编号的记录
        resp = await client.get(
            "/api/v1/testing-plans", headers=auth, params={"filters": filters, "size": 50},
        )
        occupied = [p for p in resp.json()["items"] if p["ticket_id"] == manual]
        assert len(occupied) == 1, occupied
    finally:
        resp = await client.get(
            "/api/v1/testing-plans", headers=auth, params={"filters": filters, "size": 50},
        )
        for p in resp.json()["items"]:
            await client.delete(f"/api/v1/testing-plans/{p['id']}", headers=auth)


async def test_concurrent_report_save_keeps_single_writer(client: AsyncClient, auth: dict):
    """双端同时保存报告：恰好一个成功、一个 409，revision 只 +1，内容不被静默覆盖。"""
    resp = await client.post(
        "/api/v1/reports", headers=auth,
        json={"title": "并发保存报告", "sections": [
            {"title": "章节", "order": 0, "content_html": "<p>初始</p>"},
        ]},
    )
    assert resp.status_code == 200, resp.text
    report = resp.json()
    report_id = report["id"]
    revision = report["revision"]

    def body(marker: str) -> dict:
        return {
            "title": f"并发保存报告-{marker}", "revision": revision,
            "sections": [{"title": "章节", "order": 0, "content_html": f"<p>{marker}</p>"}],
        }

    a, b = await asyncio.gather(
        client.put(f"/api/v1/reports/{report_id}", headers=auth, json=body("A")),
        client.put(f"/api/v1/reports/{report_id}", headers=auth, json=body("B")),
    )
    codes = sorted([a.status_code, b.status_code])
    assert codes == [200, 409], (a.status_code, b.status_code, a.text, b.text)

    final = await client.get(f"/api/v1/reports/{report_id}", headers=auth)
    assert final.status_code == 200
    detail = final.json()
    assert detail["revision"] == revision + 1  # 只有一个写入者生效
    winner = "A" if a.status_code == 200 else "B"
    assert detail["title"] == f"并发保存报告-{winner}"
    assert f"<p>{winner}</p>" in detail["sections"][0]["content_html"]


async def test_concurrent_batch_confirm_is_idempotent(client: AsyncClient, auth: dict):
    """同批次并发确认：只有一次真正入库，另一次幂等返回，不产生重复章节/漏洞/报告。"""
    system = "并发确认系统"
    batch_id = await _upload_report_batch(
        client, auth, system, "并发确认报告.docx",
    )
    detail = (await client.get(f"/api/v1/imports/{batch_id}", headers=auth)).json()
    record_ids = [r["id"] for r in detail["records"]]
    payload = {"record_ids": record_ids}

    first, second = await asyncio.gather(
        client.post(f"/api/v1/imports/{batch_id}/confirm", headers=auth, json=payload),
        client.post(f"/api/v1/imports/{batch_id}/confirm", headers=auth, json=payload),
    )
    codes = sorted([first.status_code, second.status_code])
    assert codes == [200, 200], (first.text, second.text)
    created = sorted([first.json()["created"], second.json()["created"]])
    assert created[0] == 0, (first.json(), second.json())  # 重复方不产生新记录
    assert created[1] >= 1

    # 漏洞 / 报告 / 章节都只有一份
    vulns = (await client.get(
        "/api/v1/vulns", headers=auth, params={"search": f"{system}漏洞A", "size": 50},
    )).json()["items"]
    assert len(vulns) == 1, [v["title"] for v in vulns]
    # 导入自动创建的报告标题取自文件名（不含扩展名）
    reports = (await client.get(
        "/api/v1/reports", headers=auth, params={"search": "并发确认报告", "size": 50},
    )).json()["items"]
    assert len(reports) == 1, [r["title"] for r in reports]
    report_detail = (await client.get(
        f"/api/v1/reports/{reports[0]['id']}", headers=auth,
    )).json()
    assert len(report_detail["sections"]) == 1, report_detail["sections"]

    # 串行重放：再次确认同一批次同样幂等（返回既有结果，不再写入）
    replay = await client.post(
        f"/api/v1/imports/{batch_id}/confirm", headers=auth, json=payload,
    )
    assert replay.status_code == 200, replay.text
    assert replay.json()["created"] == 0
