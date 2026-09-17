"""工单复测状态联动（工单级口径）回归测试。

背景缺陷：早期以「单份报告的章节漏洞」判定工单复测完成，工单含多份报告/多个漏洞
（如复测期间新录入、尚未纳入任何报告章节的漏洞）时，单份报告全部闭环会把**整单**误置
「复测完成」，出现「工单复测完成 + 仍有未修复漏洞」的矛盾状态。

覆盖：
- 单份报告闭环不得使工单进入复测完成（工单级口径）；
- 工单全部漏洞闭环才进入复测完成，并同步回填报告漏洞闭环派生字段；
- 工单「复测完成」后新增/关联漏洞 → 回退「复测中」；
- 漏洞回退后重开、再次闭环的往返幂等。
"""
from httpx import AsyncClient


async def _new_plan(client: AsyncClient, auth: dict, system_name: str) -> int:
    """新建工单并认领（录入/关联漏洞仅限认领者，管理员未认领同样不放行）。"""
    resp = await client.post(
        "/api/v1/testing-plans", headers=auth, json={"system_name": system_name},
    )
    assert resp.status_code == 200, resp.text
    plan_id = resp.json()["id"]
    resp = await client.post(f"/api/v1/testing-plans/{plan_id}/claim", headers=auth)
    assert resp.status_code == 200, resp.text
    return plan_id


async def _new_vulns(
    client: AsyncClient, auth: dict, plan_id: int | None, titles: list[str],
) -> list[int]:
    resp = await client.post(
        "/api/v1/vulns/batch", headers=auth,
        json={
            "asset_ids": [],
            "vulns": [
                {"title": t, "level": 20, "testing_plan_id": plan_id} for t in titles
            ],
        },
    )
    assert resp.status_code == 200, resp.text
    return [v["id"] for v in resp.json()]


async def _new_report(
    client: AsyncClient, auth: dict, plan_id: int, vul_ids: list[int], title: str,
) -> int:
    resp = await client.post(
        "/api/v1/reports/from-vulns", headers=auth,
        json={"title": title, "vul_ids": vul_ids, "testing_plan_id": plan_id},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["id"]


async def _start_retest(client: AsyncClient, auth: dict, report_id: int) -> None:
    resp = await client.post(f"/api/v1/reports/{report_id}/retest", headers=auth)
    assert resp.status_code == 200, resp.text


async def _vuln(client: AsyncClient, auth: dict, vul_id: int) -> dict:
    resp = await client.get(f"/api/v1/vulns/{vul_id}", headers=auth)
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _transition(
    client: AsyncClient, auth: dict, vul_id: int, status: int, retest_html: str | None = None,
) -> None:
    body: dict = {"status": status}
    if retest_html is not None:
        body["retest_html"] = retest_html
    resp = await client.post(f"/api/v1/vulns/{vul_id}/transition", headers=auth, json=body)
    assert resp.status_code == 200, resp.text


async def _plan(client: AsyncClient, auth: dict, plan_id: int) -> dict:
    resp = await client.get(f"/api/v1/testing-plans/{plan_id}", headers=auth)
    assert resp.status_code == 200, resp.text
    return resp.json()


async def test_single_report_closed_keeps_plan_retesting(client: AsyncClient, auth: dict):
    """工单含「纳入报告章节的漏洞 A」与「未纳入任何报告的漏洞 B」：
    A 复测闭环时工单必须保持「复测中」，仅该报告标记为漏洞已全部完成。"""
    plan_id = await _new_plan(client, auth, "单报告闭环系统")
    vul_a, vul_b = await _new_vulns(client, auth, plan_id, ["报告内漏洞A", "报告外漏洞B"])
    report_id = await _new_report(client, auth, plan_id, [vul_a], "单报告闭环报告")
    await _start_retest(client, auth, report_id)
    # 发起复测仅作用于报告关联漏洞：报告外漏洞仍为未修复
    assert (await _vuln(client, auth, vul_a))["status"] == 55
    assert (await _vuln(client, auth, vul_b))["status"] == 10

    await _transition(client, auth, vul_a, 60, "<p>复测通过，已修复</p>")

    plan = await _plan(client, auth, plan_id)
    assert plan["status"] == 50, "单份报告闭环不得把整单置为复测完成"
    assert plan["retest_done_time"] == ""
    # 报告维度仍可见「本报告漏洞已全部完成」，与工单状态区分
    brief = next(r for r in plan["reports"] if r["id"] == report_id)
    assert (brief["vul_total"], brief["vul_closed"], brief["all_closed"]) == (1, 1, True)


async def test_plan_completes_only_when_all_vulns_closed(client: AsyncClient, auth: dict):
    """工单全部关联漏洞闭环（已修复/已忽略）后才进入「复测完成」，并打复测完成时间。"""
    plan_id = await _new_plan(client, auth, "全部闭环系统")
    vul_a, vul_b = await _new_vulns(client, auth, plan_id, ["全部闭环漏洞A", "全部闭环漏洞B"])
    report_id = await _new_report(client, auth, plan_id, [vul_a, vul_b], "全部闭环报告")
    await _start_retest(client, auth, report_id)

    await _transition(client, auth, vul_a, 60, "<p>复测通过</p>")
    plan = await _plan(client, auth, plan_id)
    assert plan["status"] == 50
    brief = next(r for r in plan["reports"] if r["id"] == report_id)
    assert (brief["vul_total"], brief["vul_closed"], brief["all_closed"]) == (2, 1, False)

    await _transition(client, auth, vul_b, 20)  # 已忽略
    plan = await _plan(client, auth, plan_id)
    assert plan["status"] == 60
    assert plan["retest_done_time"]
    brief = next(r for r in plan["reports"] if r["id"] == report_id)
    assert (brief["vul_total"], brief["vul_closed"], brief["all_closed"]) == (2, 2, True)


async def test_done_plan_reverts_when_new_vuln_added(client: AsyncClient, auth: dict):
    """工单已「复测完成」后新增未闭环漏洞 → 回退「复测中」；再次闭环后恢复「复测完成」。"""
    plan_id = await _new_plan(client, auth, "完成后新增漏洞系统")
    (vul_a,) = await _new_vulns(client, auth, plan_id, ["完成后新增漏洞A"])
    report_id = await _new_report(client, auth, plan_id, [vul_a], "完成后新增漏洞报告")
    await _start_retest(client, auth, report_id)
    await _transition(client, auth, vul_a, 60, "<p>复测通过</p>")
    assert (await _plan(client, auth, plan_id))["status"] == 60

    # 新增未闭环漏洞：工单回退复测中
    (vul_c,) = await _new_vulns(client, auth, plan_id, ["完成后新增漏洞C"])
    plan = await _plan(client, auth, plan_id)
    assert plan["status"] == 50
    assert plan["retest_done_time"] == ""
    assert (await _vuln(client, auth, vul_c))["status"] == 10

    # 新漏洞闭环后工单再次复测完成
    await _transition(client, auth, vul_c, 20)  # 已忽略
    assert (await _plan(client, auth, plan_id))["status"] == 60


async def test_done_plan_reverts_when_existing_vuln_attached(client: AsyncClient, auth: dict):
    """工单已「复测完成」后从漏洞库关联存量未闭环漏洞 → 回退「复测中」。"""
    plan_id = await _new_plan(client, auth, "完成后关联漏洞系统")
    (vul_a,) = await _new_vulns(client, auth, plan_id, ["关联场景漏洞A"])
    report_id = await _new_report(client, auth, plan_id, [vul_a], "关联场景报告")
    await _start_retest(client, auth, report_id)
    await _transition(client, auth, vul_a, 60, "<p>复测通过</p>")
    assert (await _plan(client, auth, plan_id))["status"] == 60

    # 漏洞库中未关联工单的存量漏洞
    resp = await client.post(
        "/api/v1/vulns", headers=auth, json={"title": "关联场景存量漏洞", "level": 30},
    )
    assert resp.status_code == 200, resp.text
    loose_id = resp.json()["id"]
    resp = await client.post(
        f"/api/v1/testing-plans/{plan_id}/attach-vulns", headers=auth,
        json={"vul_ids": [loose_id]},
    )
    assert resp.status_code == 200, resp.text

    plan = await _plan(client, auth, plan_id)
    assert plan["status"] == 50
    assert plan["retest_done_time"] == ""


async def test_plan_reverts_and_recompletes_on_vuln_rollback(client: AsyncClient, auth: dict):
    """漏洞由已修复回退为未修复 → 工单回「复测中」；再次闭环 → 恢复「复测完成」（幂等往返）。"""
    plan_id = await _new_plan(client, auth, "闭环往返系统")
    (vul_a,) = await _new_vulns(client, auth, plan_id, ["闭环往返漏洞A"])
    report_id = await _new_report(client, auth, plan_id, [vul_a], "闭环往返报告")
    await _start_retest(client, auth, report_id)
    await _transition(client, auth, vul_a, 60, "<p>复测通过</p>")
    assert (await _plan(client, auth, plan_id))["status"] == 60

    # 回退：已修复 → 未修复（漏洞重新打开），工单同步回退
    await _transition(client, auth, vul_a, 10)
    plan = await _plan(client, auth, plan_id)
    assert plan["status"] == 50
    assert plan["retest_done_time"] == ""

    # 再次闭环：工单恢复复测完成（重复触发不产生异常或重复轮次）
    await _transition(client, auth, vul_a, 20)
    plan = await _plan(client, auth, plan_id)
    assert plan["status"] == 60
    assert plan["retest_round_count"] == 1
