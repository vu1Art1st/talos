"""存量报告实际人天回填脚本测试。"""
import pytest

from app.db import async_session_maker
from app.models import Report, TestingPlan as PlanModel
from scripts.backfill_report_mandays import backfill

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_backfill_report_mandays(client):
    """有效周期重算关联工单；无效周期跳过；复测报告与人工修正不影响工单汇总。"""
    async with async_session_maker() as session:
        initial_plan = PlanModel(system_name="回填初测工单", actual_mandays=0)
        override_plan = PlanModel(
            system_name="回填人工修正工单", actual_mandays=0,
            actual_mandays_override=True,
        )
        retest_plan = PlanModel(system_name="回填复测工单", actual_mandays=5)
        session.add_all([initial_plan, override_plan, retest_plan])
        await session.flush()

        initial_report = Report(
            title="回填初测报告", test_start="2026-08-03", test_end="2026-08-04",
            actual_mandays=0, testing_plan_id=initial_plan.id,
        )
        override_report = Report(
            title="回填人工修正报告", test_start="2026-08-07", test_end="2026-08-07",
            actual_mandays=0, testing_plan_id=override_plan.id,
        )
        retest_report = Report(
            title="回填复测报告", test_start="2026-08-08", test_end="2026-08-08",
            actual_mandays=0, testing_plan_id=retest_plan.id,
        )
        invalid_report = Report(
            title="回填无效周期报告", test_start="2026-08-10", test_end="2026-08-09",
            actual_mandays=0,
        )
        session.add_all([initial_report, override_report, retest_report, invalid_report])
        await session.commit()
        report_ids = [initial_report.id, override_report.id, retest_report.id, invalid_report.id]
        plan_ids = [initial_plan.id, override_plan.id, retest_plan.id]

    async with async_session_maker() as session:
        await backfill(session, dry_run=False)

    async with async_session_maker() as session:
        reports = {
            row.id: row for row in (
                await session.execute(
                    Report.__table__.select().where(Report.id.in_(report_ids))
                )
            ).mappings()
        }
        plans = {
            row.id: row for row in (
                await session.execute(
                    PlanModel.__table__.select().where(PlanModel.id.in_(plan_ids))
                )
            ).mappings()
        }
        assert reports[report_ids[0]]["actual_mandays"] == 2
        assert reports[report_ids[1]]["actual_mandays"] == 1
        assert reports[report_ids[2]]["actual_mandays"] == 1
        assert reports[report_ids[3]]["actual_mandays"] == 0
        assert plans[plan_ids[0]]["actual_mandays"] == 2
        assert plans[plan_ids[1]]["actual_mandays"] == 0
        assert plans[plan_ids[2]]["actual_mandays"] == 5

    async with async_session_maker() as session:
        await backfill(session, dry_run=False)

    async with async_session_maker() as session:
        assert (await session.get(Report, report_ids[0])).actual_mandays == 2
        assert (await session.get(Report, report_ids[3])).actual_mandays == 0
