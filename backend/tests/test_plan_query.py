"""结论输出与统计周期回归测试（2026-09-19 口径确认）。

背景（生产实测）：工单 20260721-1 初测完成 2026-07-30、复测轮次 2026-09-16 发起且复测报告同日
生成，但 `retest_done_time` 与轮次 `done_time` **均为空**（工单仍有未闭环漏洞）。旧实现的时间筛选
只看 `first_test_done_time`，导致「周期内已完成的复测」被排除、结论漏统计。

覆盖：
- 统计周期命中 = 初测完成 / 复测发起 / 复测完成 / 复测报告生成 任一落入周期；
- 结论新文案（周期括注 / 部门名 / 初测 / 复测 / 已完成整改 / 未完成整改）与计数；
- 报告维度复测三态（none / ongoing / done）、轮次源报告关联、报告管理页同口径；
- 无源报告轮次（报告导入复测 / 2.19.0 前存量）的覆盖代偿不误标无关报告；
- 结论附件列扩展。

断言均限定在**专属部门**内（共享会话库中含其它用例数据）；周期取「今天」，不依赖固定日期。
"""
from datetime import timedelta
from io import BytesIO

import pytest
from fastapi import HTTPException
from httpx import AsyncClient

from app.core.timeutil import now as tznow


async def _new_plan(
    client: AsyncClient, auth: dict, system_name: str, *, department: str = "",
    first_test_done_time: str = "",
) -> int:
    """新建工单并认领（录入/关联漏洞仅限认领者）。"""
    body = {"system_name": system_name}
    if department:
        body["department"] = department
    if first_test_done_time:
        body["first_test_done_time"] = first_test_done_time
    resp = await client.post("/api/v1/testing-plans", headers=auth, json=body)
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
            "vulns": [{"title": t, "level": 20, "testing_plan_id": plan_id} for t in titles],
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


async def _transition(client: AsyncClient, auth: dict, vul_id: int, status: int, retest_html: str = "") -> None:
    body: dict = {"status": status}
    if retest_html:
        body["retest_html"] = retest_html
    resp = await client.post(f"/api/v1/vulns/{vul_id}/transition", headers=auth, json=body)
    assert resp.status_code == 200, resp.text


async def _plan(client: AsyncClient, auth: dict, plan_id: int) -> dict:
    resp = await client.get(f"/api/v1/testing-plans/{plan_id}", headers=auth)
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _list_names(client: AsyncClient, auth: dict, params: dict) -> set[str]:
    resp = await client.get(
        "/api/v1/testing-plans", headers=auth, params={"size": 100, **params},
    )
    assert resp.status_code == 200, resp.text
    return {p["system_name"] for p in resp.json()["items"]}


async def _conclusion(client: AsyncClient, auth: dict, params: dict) -> dict:
    resp = await client.get("/api/v1/testing-plans/conclusion", headers=auth, params=params)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _today() -> str:
    """统计周期取「今天」（应用时区 UTC+8），避免依赖固定日期。"""
    return tznow().date().isoformat()


async def test_period_filter_includes_retest_actions(client: AsyncClient, auth: dict):
    """周期命中不只看初测完成：周期内发起复测 / 生成复测报告同样纳入（复刻 20260721-1 场景）。"""
    dept = "周期筛选专用部门"
    today = _today()
    await _new_plan(
        client, auth, "周期筛选系统-初测完成", department=dept, first_test_done_time=today,
    )
    retest_plan = await _new_plan(
        client, auth, "周期筛选系统-周期外初测", department=dept, first_test_done_time="2020-01-01",
    )
    vul_a, vul_b = await _new_vulns(client, auth, retest_plan, ["周期筛选漏洞A", "周期筛选漏洞B"])
    report_id = await _new_report(client, auth, retest_plan, [vul_a], "周期筛选系统渗透测试报告")
    await _start_retest(client, auth, report_id)
    # 一个漏洞复测通过、另一个仍复测中 → 工单整体未闭环（与线上 20260721-1 同形）
    await _transition(client, auth, vul_a, 60, "<p>复测通过</p>")

    scope = {"department": dept}
    assert await _list_names(
        client, auth, {**scope, "first_test_from": today, "first_test_to": today},
    ) == {"周期筛选系统-初测完成", "周期筛选系统-周期外初测"}
    # 只看 2020-01-01：命中「初测完成在周期内」的那一单，说明两条支路都在生效
    assert await _list_names(
        client, auth, {**scope, "first_test_from": "2020-01-01", "first_test_to": "2020-01-01"},
    ) == {"周期筛选系统-周期外初测"}
    # 统计端点与列表同口径
    resp = await client.get("/api/v1/testing-plans/stats", headers=auth, params={
        **scope, "first_test_from": today, "first_test_to": today,
    })
    assert resp.status_code == 200
    assert resp.json()["total_plans"] == 2


async def test_conclusion_text_and_counts(client: AsyncClient, auth: dict):
    """结论新文案与计数：部门名 / 共完成系统 / 初测 / 复测 / 已完成整改 / 未完成整改。"""
    dept = "结论文案专用部门"
    today = _today()
    await _new_plan(
        client, auth, "结论文案系统-初测完成", department=dept, first_test_done_time=today,
    )
    first_plan = (await client.get("/api/v1/testing-plans", headers=auth, params={
        "search": "结论文案系统-初测完成", "size": 5,
    })).json()["items"][0]
    await _new_vulns(client, auth, first_plan["id"], ["结论文案漏洞A"])

    retest_plan = await _new_plan(
        client, auth, "结论文案系统-复测中", department=dept, first_test_done_time="2020-01-01",
    )
    vul_a, vul_b = await _new_vulns(client, auth, retest_plan, ["结论文案漏洞B", "结论文案漏洞C"])
    report_id = await _new_report(client, auth, retest_plan, [vul_a, vul_b], "结论文案系统渗透测试报告")
    await _start_retest(client, auth, report_id)
    await _transition(client, auth, vul_a, 60, "<p>复测通过</p>")

    params = {"department": dept, "first_test_from": today, "first_test_to": today}
    data = await _conclusion(client, auth, {**params, "period_label": "本周"})
    assert data["period_text"] == "本周"
    assert data["departments"] == 1
    assert data["department_names"] == [dept]
    assert data["systems"] == 2
    assert (data["first_test_systems"], data["first_test_vulns"]) == (1, 1)
    assert data["retest_systems"] == 1
    assert (data["retest_fixed_systems"], data["retest_unfixed_systems"]) == (0, 1)
    assert data["retest_started_systems"] == 1
    assert data["retest_report_count"] == 1
    assert data["summary"] == (
        f"渗透测试方面，统计周期内（本周）共完成1个部门（{dept}）的2个系统测试工作。"
        "其中初测完成1个系统发现1个漏洞。复测完成1个系统，其中0个系统已完成整改，"
        "1个系统未完成整改仍存在漏洞未修复。请相关部门尽快完成漏洞修复并提交复测。"
        "具体漏洞情况详见附件。"
    )

    # 自定义区间（无周期名称）→ 括注回落到起止日期
    custom = await _conclusion(client, auth, params)
    assert custom["period_text"] == f"{today} - {today}"
    assert f"统计周期内（{today} - {today}）" in custom["summary"]
    # 附件行携带初测/复测完成时间，供导出扩展列使用
    row = next(r for r in custom["rows"] if r["system_name"] == "结论文案系统-复测中")
    assert row["first_test_done_time"] == "2020-01-01"
    assert row["retest_done_time"] == ""
    assert row["vuln_count"] == 2


async def test_conclusion_export_columns(client: AsyncClient, auth: dict):
    """结论附件列扩展：工单ID/部门/系统/漏洞数/测试类型/初测完成/复测完成/整改完成情况。"""
    from openpyxl import load_workbook

    dept = "结论附件专用部门"
    today = _today()
    plan_id = await _new_plan(
        client, auth, "结论附件系统", department=dept, first_test_done_time=today,
    )
    await _new_vulns(client, auth, plan_id, ["结论附件漏洞"])

    resp = await client.get("/api/v1/testing-plans/conclusion/export", headers=auth, params={
        "department": dept, "first_test_from": today, "first_test_to": today,
    })
    assert resp.status_code == 200
    rows = list(load_workbook(BytesIO(resp.content)).active.iter_rows(values_only=True))
    assert rows[0] == (
        "工单ID", "所属部门", "测试系统", "漏洞数", "测试类型",
        "初测完成时间", "复测完成时间", "整改完成情况",
    )
    assert rows[1][1] == dept
    assert rows[1][2] == "结论附件系统"
    assert rows[1][5] == today
    assert rows[1][6] in ("", None)  # 空单元格回读为 None



async def test_report_retest_state_three_states(client: AsyncClient, auth: dict):
    """报告复测三态：初测报告发起复测 → 复测中 / 章节闭环 → 复测完成；新建报告 → 未发起复测。

    注意：系统名与报告标题刻意不含「复测」二字，否则会被标题口径判为复测报告。
    """
    dept = "报告三态专用部门"
    plan_id = await _new_plan(client, auth, "报告三态系统", department=dept)
    vul_a, _vul_b = await _new_vulns(client, auth, plan_id, ["报告三态漏洞A", "报告三态漏洞B"])
    first_report = await _new_report(client, auth, plan_id, [vul_a], "报告三态系统渗透测试报告")
    await _start_retest(client, auth, first_report)

    detail = await _plan(client, auth, plan_id)
    briefs = {r["id"]: r for r in detail["reports"]}
    # 轮次记录源报告：初测报告 → 关联到本轮，复测报告由系统自动生成
    assert detail["retest_rounds"][-1]["src_report_id"] == first_report
    retest_report = next(r["id"] for r in detail["reports"] if r["is_retest"])
    assert briefs[first_report]["retest_state"] == "ongoing"
    assert briefs[retest_report]["retest_state"] == "ongoing"

    # 章节漏洞闭环 → 两份报告均为复测完成
    await _transition(client, auth, vul_a, 60, "<p>复测通过</p>")
    detail = await _plan(client, auth, plan_id)
    assert {r["retest_state"] for r in detail["reports"]} == {"done"}
    assert {r["is_retest"] for r in detail["reports"]} == {False, True}

    # 新建报告（未发起复测）→ 未发起复测；报告管理页同口径
    fresh = await _new_report(client, auth, plan_id, [vul_a], "报告三态系统渗透测试报告-新")
    detail = await _plan(client, auth, plan_id)
    assert next(r for r in detail["reports"] if r["id"] == fresh)["retest_state"] == "none"

    resp = await client.get("/api/v1/reports", headers=auth, params={"search": "报告三态系统", "size": 100})
    assert resp.status_code == 200
    states = {r["id"]: r["retest_state"] for r in resp.json()["items"]}
    assert states[first_report] == "done"
    assert states[retest_report] == "done"
    assert states[fresh] == "none"


async def test_report_retest_state_covers_import_retest_round(client: AsyncClient, auth: dict):
    """报告导入复测的存量轮次（有复测报告但无源报告）也要让同工单初测报告进入复测中/复测完成。

    背景（2026-09-22 实测）：`triggered` 原先只认轮次 `src_report_id`，而「报告导入复测」与 2.19.0
    之前的存量轮次都不带它 → 工单内所有初测报告恒为「未发起复测」（复测报告因标题含「复测」正常）。
    本用例构造该存量形态，断言读取侧覆盖代偿（本轮复测报告章节漏洞 ∩ 本报告章节漏洞）生效，
    且不含相同漏洞的其它报告不被误标。

    注意：系统名与初测报告标题刻意不含「复测」二字，否则会被标题口径判为复测报告。
    """
    dept = "覆盖代偿专用部门"
    plan_id = await _new_plan(client, auth, "覆盖代偿系统", department=dept)
    vul_a, vul_b = await _new_vulns(client, auth, plan_id, ["覆盖代偿漏洞A", "覆盖代偿漏洞B"])
    first_report = await _new_report(
        client, auth, plan_id, [vul_a, vul_b], "覆盖代偿系统渗透测试报告",
    )
    retest_report = await _new_report(
        client, auth, plan_id, [vul_a, vul_b], "覆盖代偿系统渗透测试复测报告",
    )
    other_vul, = await _new_vulns(client, auth, plan_id, ["覆盖代偿无关漏洞"])
    other_report = await _new_report(
        client, auth, plan_id, [other_vul], "覆盖代偿系统第二份渗透测试报告",
    )

    # 模拟存量数据：轮次有复测报告（report_id）但源报告为空（「报告导入复测」当时的写入形态）
    from app.db import async_session_maker
    from app.models import TestingPlanRetestRound

    async with async_session_maker() as session:
        session.add(TestingPlanRetestRound(
            plan_id=plan_id, round_no=1, source="报告导入复测", report_id=retest_report,
        ))
        await session.commit()

    async def states_of() -> dict[int, str]:
        detail = await _plan(client, auth, plan_id)
        return {r["id"]: r["retest_state"] for r in detail["reports"]}

    # 章节漏洞仍修复中（50）→ 初测报告按覆盖代偿进入「复测中」
    states = await states_of()
    assert states[first_report] == "ongoing"
    assert states[retest_report] == "ongoing"
    assert states[other_report] == "none"  # 章节漏洞未被本轮复测覆盖 → 不误标

    # 章节漏洞闭环（修复中 50 → 复测中 55 → 已修复 60）→ 复测完成；无关报告仍为未发起复测
    for vid in (vul_a, vul_b):
        await _transition(client, auth, vid, 55)
    assert (await states_of())[first_report] == "ongoing"
    for vid in (vul_a, vul_b):
        await _transition(client, auth, vid, 60, "<p>复测通过</p>")
    states = await states_of()
    assert states[first_report] == "done"
    assert states[other_report] == "none"

    # 报告管理页同口径
    resp = await client.get(
        "/api/v1/reports", headers=auth, params={"search": "覆盖代偿系统", "size": 100},
    )
    assert resp.status_code == 200, resp.text
    states = {r["id"]: r["retest_state"] for r in resp.json()["items"]}
    assert states[first_report] == "done"
    assert states[other_report] == "none"


def test_period_condition_uses_datetime_binds():
    """PG 守卫：周期的 DateTime 分支必须绑日期时间参数，禁止在列上套 `date()` 比日期串。

    背景（2026-09-19 线上 500）：`func.date(col) >= '2026-09-14'` 会把日期串按 VARCHAR 绑定，
    PostgreSQL 不存在 `date >= character varying` 算子（asyncpg 直接抛 UndefinedFunctionError）。
    测试库自 2026-09-21 起同为 PostgreSQL，但接口级用例只在「恰好走到该分支且数据非空」时才暴露，
    静态方言编译断言能更早、更准地失败，故保留为快速反馈守卫。
    """
    from sqlalchemy import select
    from sqlalchemy.dialects import postgresql

    from app.models import TestingPlan, TestingPlanRetestRound
    from app.services import plan_query

    start = plan_query._day_start("2026-09-14")
    end = plan_query._day_start("2026-09-19") + timedelta(days=1)
    helper = select(TestingPlanRetestRound.id).where(
        plan_query._datetime_date_range(TestingPlanRetestRound.start_time, start, end)
    )
    compiled = helper.compile(dialect=postgresql.dialect())
    assert {type(b.type).__name__ for b in compiled.binds.values()} == {"DateTime"}
    sql = str(compiled)
    assert "date(" not in sql  # 列上不得套函数
    assert "start_time >= " in sql and "start_time < " in sql  # 半开区间 [起, 次日)

    # 完整周期条件同样不得出现 date()，防止回退到「日期串 vs DateTime 列」比较
    cond = plan_query.plan_conditions(first_test_from="2026-09-14", first_test_to="2026-09-19")
    full = str(select(TestingPlan.id).where(*cond).compile(dialect=postgresql.dialect()))
    assert "date(" not in full

    # 非法日期：明确 400，而不是 500 或静默返回空结果
    with pytest.raises(HTTPException) as err:
        plan_query._period_condition("2026-09-14", "not-a-date")
    assert err.value.status_code == 400
