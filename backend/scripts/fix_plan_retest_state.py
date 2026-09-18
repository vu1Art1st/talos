"""存量工单复测状态纠偏：把「已复测完成但仍存在未闭环漏洞」的工单回退为「复测中」。

背景：早期 `vul_service.sync_plan_retest_state`（原 `sync_report_completion`）以「单份报告的
章节漏洞」为口径判定工单复测完成，工单含多份报告/多个漏洞（如复测期间新录入、尚未纳入任何
报告章节的漏洞）时会把整单误置「复测完成」，出现「工单复测完成 + 仍有未修复漏洞」的矛盾状态。

本脚本按**工单级**口径幂等纠偏：
- status=60（复测完成）且工单存在未闭环漏洞（非 已修复/已忽略）→ 置 50（复测中）、
  清空 retest_done_time、撤销最近一轮复测完成点；
- 工单无关联漏洞、或漏洞已全部闭环 → 不动（不反向把 50 改为 60，避免覆盖人工状态）。

执行前自动把将被修改的工单原值备份到 `storage/backups/`（JSON），便于回滚复核。

用法（backend/ 目录，或容器内 /app）：
    python -m scripts.fix_plan_retest_state            # 执行纠偏（自动备份）
    python -m scripts.fix_plan_retest_state --dry-run  # 仅打印将纠偏的工单，不落库
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.constants import PlanStatus, VulStatus  # noqa: E402
from app.db import async_session_maker  # noqa: E402
from app.models import TestingPlan, Vul  # noqa: E402
from app.services import plan_service  # noqa: E402
from scripts._common import dry_run_flag, run, save_backup  # noqa: E402

CLOSED_STATUSES = (VulStatus.IGNORED, VulStatus.FIXED)


async def main(dry_run: bool = False) -> None:
    async with async_session_maker() as session:
        plans = (
            await session.execute(
                select(TestingPlan).where(TestingPlan.status == PlanStatus.RETEST_DONE)
            )
        ).scalars().all()

        # 纯数据快照：dry-run 的 rollback 会使会话内 ORM 实例过期（异步会话再访问会抛
        # MissingGreenlet），故先取出为普通 dict；约定见 scripts/_common.run() 的 docstring。
        pending: list[dict] = []
        for plan in plans:
            statuses = (
                await session.execute(
                    select(Vul.status).where(Vul.testing_plan_id == plan.id)
                )
            ).scalars().all()
            if not statuses:
                continue
            open_cnt = sum(1 for s in statuses if s not in CLOSED_STATUSES)
            if open_cnt == 0:
                continue
            pending.append({
                "id": plan.id,
                "ticket_id": plan.ticket_id,
                "system_name": plan.system_name,
                "before_status": int(plan.status),
                "before_retest_done_time": plan.retest_done_time or "",
                "vul_total": len(statuses),
                "vul_open": open_cnt,
                "after_status": int(PlanStatus.RETESTING),
                "after_retest_done_time": "",
            })

        print(f"「复测完成」工单：{len(plans)} 个；待纠偏（仍有未闭环漏洞）：{len(pending)} 个")
        for row in pending:
            print(
                f"  - 工单 {row['ticket_id'] or row['id']}（{row['system_name']}）"
                f"漏洞 {row['vul_total']} 个 / 未闭环 {row['vul_open']} 个"
                f" → 复测完成({row['before_status']}) → 复测中({row['after_status']})"
            )
        if not pending:
            print("无需纠偏。")
            return
        if dry_run:
            await session.rollback()
            print("[dry-run] 未落库。")
            return

        backup_file = save_backup(pending, "plan_retest_state")
        print(f"原值已备份：{backup_file}")

        for row in pending:
            plan = await session.get(TestingPlan, row["id"])
            if plan is None:
                continue
            plan.status = PlanStatus.RETESTING
            plan.retest_done_time = ""
            # 撤销最近一轮完成点，保持轮次状态与工单状态一致
            plan_service.reopen_retest_round(plan)
        await session.commit()
        print(f"纠偏完成：{len(pending)} 个工单已回退「复测中」。")


if __name__ == "__main__":
    # 统一入口：静默 SQLAlchemy 回显 + `--dry-run` 解析（审计 M-2）
    run(main, dry_run=dry_run_flag())
