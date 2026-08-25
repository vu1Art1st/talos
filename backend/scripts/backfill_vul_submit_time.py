"""存量 Word 导入漏洞提交时间更正：统一回填为导入报告时间（标题日期 14:00）。

背景：报告格式导入建漏洞时，提交时间此前取导入当天当前时间，导致渗透测试工单
按月漏洞表单与安全态势按导入当月归口。修复代码后新导入已按报告时间落库；
本脚本幂等扫描历史已确认的报告导入批次，把其关联漏洞的 submit_time 回填为
批次 meta.report_date 的 14:00（与报告 create_time 口径一致）。

用法（backend/ 目录，或容器内 /app）：
    python -m scripts.backfill_vul_submit_time            # 执行回填
    python -m scripts.backfill_vul_submit_time --dry-run  # 仅统计待回填数量，不落库
"""
import asyncio
import logging
import sys
from datetime import datetime, time as dtime
from pathlib import Path

# 静默 SQLAlchemy 调试回显，保持回填输出简洁
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.db import async_session_maker  # noqa: E402
from app.models import ImportBatch, ImportRecord, Vul  # noqa: E402


async def main(dry_run: bool = False) -> None:
    async with async_session_maker() as session:
        batches = (
            await session.execute(
                select(ImportBatch).where(
                    ImportBatch.doc_kind == "report",
                    ImportBatch.status == "confirmed",
                )
            )
        ).scalars().all()
        updated = skipped = 0
        for batch in batches:
            report_date = (batch.meta_json or {}).get("report_date") or ""
            try:
                target = datetime.combine(
                    datetime.strptime(report_date, "%Y-%m-%d").date(), dtime(14, 0)
                )
            except ValueError:
                skipped += 1
                continue
            vul_ids = (
                await session.execute(
                    select(ImportRecord.vul_id).where(
                        ImportRecord.batch_id == batch.id,
                        ImportRecord.vul_id.is_not(None),
                    )
                )
            ).scalars().all()
            for vul_id in vul_ids:
                vul = await session.get(Vul, vul_id)
                if vul is None or vul.submit_time == target:
                    continue
                vul.submit_time = target
                updated += 1
        if dry_run:
            await session.rollback()
            print(f"[dry-run] 待回填 {updated} 条漏洞提交时间；跳过批次 {skipped}（缺 report_date）")
        else:
            await session.commit()
            print(f"回填完成：已更新 {updated} 条漏洞提交时间；跳过批次 {skipped}（缺 report_date）")


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    asyncio.run(main(dry_run=dry_run))
