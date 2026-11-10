"""存量工单复测结果纠偏：按当前口径补记「复测未通过」。

扫描仍为「复测中」的工单并调用 `vul_service.sync_plan_retest_state`：
- 当前复测轮次已有报告、全部漏洞均已形成复测结论且仍有未闭环漏洞 → 复测未通过(65)；
- 全部漏洞已闭环 → 复测完成(60)；
- 仍有漏洞未形成复测结论 → 保持复测中(50)。

脚本幂等，默认执行前把原值备份到 `storage/backups/`。

用法（backend/ 目录，或容器内 /app）：
    python -m scripts.backfill_plan_retest_failed --dry-run
    python -m scripts.backfill_plan_retest_failed
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.constants import PlanStatus  # noqa: E402
from app.db import async_session_maker  # noqa: E402
from app.models import TestingPlan  # noqa: E402
from app.services import vul_service  # noqa: E402
from scripts._common import dry_run_flag, run, save_backup  # noqa: E402


async def main(dry_run: bool = False) -> None:
    async with async_session_maker() as session:
        plans = (
            await session.execute(
                select(TestingPlan)
                .where(TestingPlan.status == PlanStatus.RETESTING)
                .order_by(TestingPlan.id)
            )
        ).scalars().all()
        before = {
            plan.id: {
                "id": plan.id,
                "ticket_id": plan.ticket_id,
                "system_name": plan.system_name,
                "status": int(plan.status),
                "retest_done_time": plan.retest_done_time or "",
            }
            for plan in plans
        }
        for plan_id in before:
            await vul_service.sync_plan_retest_state(session, plan_ids=[plan_id])

        changed: list[dict] = []
        for plan_id, old in before.items():
            plan = await session.get(TestingPlan, plan_id)
            if plan is None or int(plan.status) == old["status"]:
                continue
            changed.append({
                **old,
                "after_status": int(plan.status),
                "after_retest_done_time": plan.retest_done_time or "",
            })

        print(f"「复测中」工单：{len(plans)} 个；待纠偏：{len(changed)} 个")
        for row in changed:
            print(
                f"  - 工单 {row['ticket_id'] or row['id']}（{row['system_name']}）"
                f" 状态 {row['status']} → {row['after_status']}"
            )
        if not changed:
            print("无需纠偏。")
            await session.rollback()
            return
        if dry_run:
            await session.rollback()
            print("[dry-run] 未落库。")
            return

        backup_file = save_backup(changed, "plan_retest_failed")
        print(f"原值已备份：{backup_file}")
        await session.commit()
        print(f"纠偏完成：{len(changed)} 个工单已按复测结论更新状态。")


if __name__ == "__main__":
    run(main, dry_run=dry_run_flag())
