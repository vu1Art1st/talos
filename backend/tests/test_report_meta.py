"""导出 meta 单一实现（services/report_meta）回归测试。

背景缺陷（2026-09-17 代码审计 B-1/B-2）：导入后自动导出（services/import_service）
与手动导出（workers/main）各自实现一份 meta / 版本记录 / 章节 / 漏洞与资产构建，
并已产生口径分叉：
- 版本变更记录日期在「当前报告」分支是否回退 report.create_time；
- meta.report_time（封面与版本记录基准）是否注入；
- 复测判定在 4 处内联 `"复测" in title`，绕过 plan_service.is_retest_report_title。

覆盖：
- meta 由 report_meta 单一构建，report_time / generator 为显式参数（None = 不注入）；
- 复测判定口径统一（plan_service.is_retest_report_title）；
- 版本记录日期口径：最近成功导出时间 > 报告自身日期 > 导出当天（当前报告）/ 空（其他报告）；
- 源码级不变量：两处导出入口不得再内联复测判定或自行拼装 report_records。
"""
from datetime import datetime
from pathlib import Path

from httpx import AsyncClient

_APP_DIR = Path(__file__).resolve().parents[1] / "app"


async def _new_plan(client: AsyncClient, auth: dict, name: str) -> int:
    resp = await client.post("/api/v1/testing-plans", headers=auth, json={"system_name": name})
    assert resp.status_code == 200, resp.text
    plan_id = resp.json()["id"]
    resp = await client.post(f"/api/v1/testing-plans/{plan_id}/claim", headers=auth)
    assert resp.status_code == 200, resp.text
    return plan_id


async def _new_vulns(
    client: AsyncClient, auth: dict, plan_id: int, titles: list[str],
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


async def test_build_export_meta_flags_and_dates(client: AsyncClient, auth: dict):
    from app.db import async_session_maker
    from app.models import ExportJob, Report, TestingPlan
    from app.services import report_meta

    plan_id = await _new_plan(client, auth, "导出meta口径回归工单")
    vul_ids = await _new_vulns(client, auth, plan_id, ["SQL注入", "越权访问"])
    first_id = await _new_report(client, auth, plan_id, vul_ids, "某某系统渗透测试报告")
    retest_id = await _new_report(client, auth, plan_id, vul_ids, "某某系统渗透测试复测报告")

    async with async_session_maker() as session:
        plan = await session.get(TestingPlan, plan_id)
        first = await session.get(Report, first_id)
        retest = await session.get(Report, retest_id)

        # 1) report_time / generator 为显式参数：手动导出口径两者都不注入
        meta_manual = await report_meta.build_export_meta(session, first, plan=plan)
        assert "report_time" not in meta_manual
        assert "generator" not in meta_manual

        # 导入自动导出口径：注入报告时间；空串 generator 属「有值」，同样注入
        stamp = datetime(2026, 3, 4, 14, 0)
        meta_import = await report_meta.build_export_meta(
            session, first, plan=plan, generator="", report_time=stamp,
        )
        assert meta_import["report_time"] == stamp
        assert meta_import["generator"] == ""

        # 2) 复测判定口径统一（B-2）：同一函数判定初测/复测报告
        assert meta_manual["is_retest"] is False
        assert (await report_meta.build_export_meta(session, retest, plan=plan))["is_retest"] is True

        # 3) 版本记录：按 (create_time, id) 升序 → 初测在前、复测在后
        records = meta_manual["report_records"]
        assert [r["is_retest"] for r in records] == [False, True]
        # 无成功导出记录时，日期回退报告自身日期
        assert records[0]["date"] == first.create_time.strftime("%Y-%m-%d")
        assert records[1]["date"] == retest.create_time.strftime("%Y-%m-%d")

        # 4) 初测报告存在「已成功导出」记录后：其他报告取该日期，当前报告无导出仍取自身日期
        session.add(ExportJob(
            report_id=first_id, title=first.title, fmt="docx", status="done",
            file_path="placeholder.docx", finish_time=datetime(2020, 5, 6, 10, 0),
        ))
        await session.flush()
        records2 = (await report_meta.build_export_meta(session, retest, plan=plan))["report_records"]
        assert records2[0]["date"] == "2020-05-06"
        assert records2[1]["date"] == retest.create_time.strftime("%Y-%m-%d")
        # 本次插入的导出记录不落库，避免影响其他用例
        await session.rollback()


def test_export_entrypoints_share_single_implementation():
    """源码级不变量：两处导出入口不得再内联复测判定或自行拼装 report_records。"""
    targets = {
        "services/import_service.py": (_APP_DIR / "services" / "import_service.py").read_text(encoding="utf-8"),
        "workers/main.py": (_APP_DIR / "workers" / "main.py").read_text(encoding="utf-8"),
    }
    for name, src in targets.items():
        assert '"复测" in (' not in src, (
            f"{name} 仍内联复测判定，应调用 plan_service.is_retest_report_title"
        )
        assert 'meta["report_records"]' not in src, (
            f"{name} 仍自行拼装 report_records，应调用 services.report_meta"
        )
        assert "report_meta" in src, f"{name} 未使用 services.report_meta"

    meta_src = (_APP_DIR / "services" / "report_meta.py").read_text(encoding="utf-8")
    assert "is_retest_report_title" in meta_src, "复测判定唯一来源应为 plan_service.is_retest_report_title"
