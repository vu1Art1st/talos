"""存量报告实际人天回填：修复测试周期有效但 `actual_mandays=0` 的报告。

历史报告功能上线时只给 `reports.actual_mandays` 填了默认值 0，未按已有测试周期回填，
导致关联工单的自动人天也保持为 0。本脚本幂等扫描候选报告并复用
`core.timeutil.mandays_between` 重算；随后刷新关联工单，已人工修正的工单保持不变。

用法（backend/ 目录，或容器内 /app）：
    python -m scripts.backfill_report_mandays            # 执行回填（自动备份）
    python -m scripts.backfill_report_mandays --dry-run  # 仅统计，不落库
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.core.timeutil import mandays_between  # noqa: E402
from app.db import async_session_maker  # noqa: E402
from app.models import Report, TestingPlan  # noqa: E402
from app.services import plan_service  # noqa: E402
from scripts._common import dry_run_flag, run, save_backup  # noqa: E402


async def backfill(session, dry_run: bool = False) -> tuple[int, int]:
    """执行回填，返回（更新报告数、刷新工单数）。调用方负责会话生命周期。"""
    reports = (
        await session.execute(
            select(Report).where(
                Report.actual_mandays == 0,
                Report.test_start != "",
                Report.test_end != "",
            ).order_by(Report.id)
        )
    ).scalars().all()
    pending: list[tuple[Report, float]] = []
    snapshots: list[dict] = []
    affected_plans: set[int] = set()
    for report in reports:
        recalculated = mandays_between(report.test_start, report.test_end)
        if recalculated <= 0:
            continue
        plan = (
            await session.get(TestingPlan, report.testing_plan_id)
            if report.testing_plan_id is not None else None
        )
        pending.append((report, recalculated))
        if plan is not None:
            affected_plans.add(plan.id)
        snapshots.append({
            "report_id": report.id,
            "plan_id": report.testing_plan_id,
            "test_start": report.test_start,
            "test_end": report.test_end,
            "old_report_mandays": report.actual_mandays,
            "new_report_mandays": recalculated,
            "old_plan_mandays": plan.actual_mandays if plan is not None else None,
            "plan_override": plan.actual_mandays_override if plan is not None else None,
        })

    if dry_run:
        await session.rollback()
        print(f"[dry-run] 待重算报告 {len(pending)} 份，关联工单 {len(affected_plans)} 个（未落库）")
        return len(pending), len(affected_plans)

    backup_file = save_backup(snapshots, "report_actual_mandays")
    for report, recalculated in pending:
        report.actual_mandays = recalculated
    await session.flush()
    for plan_id in sorted(affected_plans):
        await plan_service.refresh_mandays(session, plan_id)
    await session.commit()
    print(f"回填完成：重算报告 {len(pending)} 份，刷新关联工单 {len(affected_plans)} 个")
    if backup_file:
        print(f"原值备份：{backup_file}")
    return len(pending), len(affected_plans)


async def main(dry_run: bool = False) -> None:
    async with async_session_maker() as session:
        await backfill(session, dry_run=dry_run)


if __name__ == "__main__":
    run(main, dry_run=dry_run_flag())
