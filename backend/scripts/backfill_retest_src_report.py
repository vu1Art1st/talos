"""存量复测轮次回填「源报告」外键：`testing_plan_retest_rounds.src_report_id`。

背景：报告与复测轮次原先只有 `report_id`（指向本轮新生成的复测报告）与 `source` 自由文本，
无法可靠回答「某份初测报告是否已发起过复测」。新字段 `src_report_id` 由发起复测入口写入，
本脚本按两条口径回填存量轮次（先后顺序即可靠度顺序）：

1. **source 文本**：`报告《<标题>》发起复测` 且该标题在**同工单**内唯一命中（跨工单重名不猜测）；
2. **章节漏洞交集**：本轮有复测报告（`report_id`）时，复用 `plan_service.infer_src_report_id`
   的同一规则（同工单、标题不含「复测」、交集最大且唯一）——覆盖「报告导入复测」轮次。

判定与幂等：只处理 `src_report_id IS NULL` 的轮次；两条口径都无唯一结论时保持为空并打印待人工确认
（「手动流转至复测中」等无复测报告的轮次按设计保持为空）。重复执行结果一致。

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
from app.services import plan_service  # noqa: E402
from scripts._common import dry_run_flag, run, save_backup  # noqa: E402

# 发起复测时写入的 source 格式（见 api/v1/reports.py::retest_report）
_SOURCE_PATTERN = re.compile(r"^报告《(.+)》发起复测$")


def match_by_source(
    round_row: TestingPlanRetestRound, by_title: dict[str, list[Report]],
) -> tuple[int | None, str]:
    """口径 1：按 source 文本在同工单内唯一匹配源报告；返回 (源报告 id 或 None, 判定说明)。"""
    m = _SOURCE_PATTERN.match((round_row.source or "").strip())
    if m is None:
        return None, f"source 非发起复测格式（{round_row.source or '空'}）"
    same_plan = [
        c for c in by_title.get(m.group(1), []) if c.testing_plan_id == round_row.plan_id
    ]
    if len(same_plan) != 1:
        return None, f"文本标题在同工单内命中 {len(same_plan)} 份"
    return same_plan[0].id, "source 文本"


async def resolve_src_report_id(
    session, round_row: TestingPlanRetestRound, by_title: dict[str, list[Report]],
) -> tuple[int | None, str]:
    """依次套用两条口径；口径 1 未定论且本轮有复测报告时，用章节漏洞交集（口径 2）。"""
    src_id, how = match_by_source(round_row, by_title)
    if src_id is None and round_row.report_id is not None:
        src_id = await plan_service.infer_src_report_id(
            session, round_row.plan_id, round_row.report_id
        )
        how = f"{how}；章节漏洞交集{'命中' if src_id else '无唯一最大'}"
    return src_id, how


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
            src_id, how = await resolve_src_report_id(session, r, by_title)
            if src_id is None:
                # 无匹配（报告已删/改标题）或多义（同工单重名）→ 不猜测，打印待人工确认
                skipped.append(f"轮次 {r.id}（工单 {r.plan_id}）：{how}")
                continue
            snapshot.append({
                "round_id": r.id, "plan_id": r.plan_id,
                "source": r.source, "src_report_id": src_id,
            })
            pending.append((r, src_id))
            # 标记用 ASCII：Windows GBK 控制台打印非 ASCII 符号会 UnicodeEncodeError
            print(f"  [!] 轮次 {r.id}（工单 {r.plan_id}）→ 源报告 {src_id}（{how}）")

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
