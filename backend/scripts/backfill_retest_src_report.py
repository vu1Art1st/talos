"""存量复测轮次回填「源报告」外键：`testing_plan_retest_rounds.src_report_id`。

背景：报告与复测轮次原先只有 `report_id`（指向本轮新生成的复测报告）与 `source` 自由文本，
无法可靠回答「某份初测报告是否已发起过复测」。新字段 `src_report_id` 由发起复测入口写入，
本脚本按 `source` 文本（约定格式「报告《<标题>》发起复测」）回填存量轮次。

判定与幂等：只处理 `src_report_id IS NULL` 且 `source` 命中该格式的轮次；标题在**同工单**内
唯一匹配时回填（跨工单重名时不做猜测，留人工处理）。「报告导入复测」「手动流转至复测中」
等无源报告的轮次保持为空。重复执行结果一致。

执行前把待改轮次的原值备份到 `storage/backups/`（JSON），便于回滚复核。

用法（backend/ 目录，或容器内 /app）：
    python -m scripts.backfill_retest_src_report            # 执行回填（自动备份）
    python -m scripts.backfill_retest_src_report --dry-run  # 仅统计与打印，不落库
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.db import async_session_maker  # noqa: E402
from app.models import Report, TestingPlanRetestRound  # noqa: E402
from scripts._common import dry_run_flag, run, save_backup  # noqa: E402

# 发起复测时写入的 source 格式（见 api/v1/reports.py::retest_report）
_SOURCE_PATTERN = re.compile(r"^报告《(.+)》发起复测$")


async def main(dry_run: bool = False) -> None:
    async with async_session_maker() as session:
        rounds = (
            await session.execute(
                select(TestingPlanRetestRound).order_by(TestingPlanRetestRound.id)
            )
        ).scalars().all()
        reports = (await session.execute(select(Report))).scalars().all()
        by_title: dict[str, list[Report]] = {}
        for rep in reports:
            by_title.setdefault(rep.title, []).append(rep)

        snapshot: list[dict] = []
        pending: list[tuple[TestingPlanRetestRound, int]] = []
        skipped: list[str] = []
        for r in rounds:
            if r.src_report_id is not None:
                continue
            m = _SOURCE_PATTERN.match((r.source or "").strip())
            if m is None:
                continue
            same_plan = [
                c for c in by_title.get(m.group(1), []) if c.testing_plan_id == r.plan_id
            ]
            if len(same_plan) != 1:
                # 无匹配（报告已删/改标题）或多义（同工单重名）→ 不猜测，打印待人工确认
                skipped.append(f"轮次 {r.id}（工单 {r.plan_id}）：候选 {len(same_plan)} 个")
                continue
            snapshot.append({
                "round_id": r.id, "plan_id": r.plan_id,
                "source": r.source, "src_report_id": same_plan[0].id,
            })
            pending.append((r, same_plan[0].id))
            # 标记用 ASCII：Windows GBK 控制台打印非 ASCII 符号会 UnicodeEncodeError
            print(f"  [!] 轮次 {r.id}（工单 {r.plan_id}）→ 源报告 {same_plan[0].id}")

        print(f"复测轮次共 {len(rounds)} 条，其中待回填源报告 {len(pending)} 条")
        for line in skipped:
            print(f"  [skip] {line}")

        if dry_run:
            await session.rollback()
            print(f"[dry-run] 待回填 {len(pending)} 条（未落库）")
            return

        backup_file = save_backup(snapshot, "retest_round_src_report")
        for row, src_report_id in pending:
            row.src_report_id = src_report_id
        await session.commit()
        print(f"回填完成：{len(pending)} 条轮次已关联源报告")
        if backup_file:
            print(f"原值备份：{backup_file}")


if __name__ == "__main__":
    run(main, dry_run=dry_run_flag())
