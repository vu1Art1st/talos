"""存量报告章节顺序修复：按导入解析序号（import_records.seq）重排 report_sections.order。

背景：报告格式导入确认入库时，处理顺序此前未按文档序号排序（生产 PostgreSQL 返回
顺序不定），导致章节 order 被按乱序写入——报告编辑页「章节导航」与导出 Word 章节
顺序与原报告不一致。代码修复后新导入已正确；本脚本幂等扫描全部报告，把通过 Word
导入产生的章节（report_sections.vul_id → import_records.vul_id → seq）按解析序号
重排；无导入记录的章节（手工添加）保持既有相对顺序排在导入章节之后。

用法（backend/ 目录，或容器内 /app）：
    python -m scripts.repair_report_section_order            # 执行修复
    python -m scripts.repair_report_section_order --dry-run  # 仅统计将被修正的章节数，不落库
"""
import asyncio
import logging
import sys
from pathlib import Path

# 静默 SQLAlchemy 调试回显，保持修复输出简洁
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.db import async_session_maker  # noqa: E402
from app.models import ImportRecord, Report, ReportSection  # noqa: E402


async def main(dry_run: bool = False) -> None:
    async with async_session_maker() as session:
        reports = (
            await session.execute(
                select(Report).where(
                    Report.id.in_(select(ReportSection.report_id).distinct())
                )
            )
        ).scalars().all()
        fixed_reports = fixed_sections = 0
        for report in reports:
            # relationship 已按 order 排序加载
            sections = list(report.sections)
            if len(sections) < 2:
                continue
            vul_ids = [s.vul_id for s in sections if s.vul_id]
            if not vul_ids:
                continue
            # vul_id → 解析序号（同一漏洞可能在多个批次被确认，取最小 seq 即首次导入序号）
            rows = (
                await session.execute(
                    select(ImportRecord.vul_id, ImportRecord.seq).where(
                        ImportRecord.vul_id.in_(vul_ids),
                    )
                )
            ).all()
            seq_by_vul: dict[int, int] = {}
            for vul_id, seq in rows:
                if vul_id is None:
                    continue
                if vul_id not in seq_by_vul or seq < seq_by_vul[vul_id]:
                    seq_by_vul[vul_id] = seq
            # 导入章节按 seq 升序排前，手工章节保持现有相对顺序排后
            mapped = sorted(
                (s for s in sections if s.vul_id in seq_by_vul),
                key=lambda s: seq_by_vul[s.vul_id],  # type: ignore[arg-type]
            )
            unmapped = [s for s in sections if s.vul_id not in seq_by_vul]
            new_order = {s.id: i for i, s in enumerate([*mapped, *unmapped])}
            changed = [
                s for s in sections if new_order.get(s.id, s.order) != s.order
            ]
            if not changed:
                continue
            fixed_reports += 1
            fixed_sections += len(changed)
            for s in sections:
                s.order = new_order.get(s.id, s.order)
        if dry_run:
            await session.rollback()
            print(f"[dry-run] 待修正 {fixed_reports} 份报告共 {fixed_sections} 个章节顺序")
        else:
            await session.commit()
            print(f"修复完成：已修正 {fixed_reports} 份报告共 {fixed_sections} 个章节顺序")


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    asyncio.run(main(dry_run=dry_run))
