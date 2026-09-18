"""存量报告章节「复测详情」副本清理：剥离 report_sections.content_html 尾部内嵌的复测详情段。

背景：早期 `vuln_section_html` 会把 `vul.retest_html` 追加为章节正文的最后一个元素，
导致同一份复测详情既内嵌在章节正文（漏洞详情框）尾部、又存在于漏洞字段
`vulns.retest_html`（复测详情框），界面重复展示；且章节快照不随复测更新，导出时因
「正文已含复测详情」跳过追加最新内容，造成导出遗漏最新复测结果。

代码修复后新生成章节已不再内嵌；本脚本幂等清理存量数据。剥离仅针对正文中最后一次
出现的「复测详情」标记：若正文尾部确实以其开头则按精确边界剥离（保留其后手工追加的
内容），否则丢弃标记之后的全部内容。复测信息本身以 `vul.retest_html` 为准，不会丢失。

执行前自动把被修改章节的原值备份到 `storage/backups/`（JSON），便于回滚复核。

用法（backend/ 目录，或容器内 /app）：
    python -m scripts.fix_retest_section_dup            # 执行清理（自动备份）
    python -m scripts.fix_retest_section_dup --dry-run  # 仅统计将清理的章节数，不落库
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.db import async_session_maker  # noqa: E402
from app.models import ReportSection, Vul  # noqa: E402
from app.services.report_html import RETEST_LABEL_HTML, strip_embedded_retest  # noqa: E402
from scripts._common import dry_run_flag, run, save_backup  # noqa: E402


async def main(dry_run: bool = False) -> None:
    async with async_session_maker() as session:
        sections = (
            await session.execute(
                select(ReportSection).where(
                    ReportSection.content_html.like(f"%{RETEST_LABEL_HTML}%")
                )
            )
        ).scalars().all()
        print(f"含内嵌复测详情段的章节：{len(sections)} 个")

        vul_ids = [s.vul_id for s in sections if s.vul_id]
        retest_by_vul: dict[int, str] = {}
        if vul_ids:
            rows = (
                await session.execute(
                    select(Vul.id, Vul.retest_html).where(Vul.id.in_(vul_ids))
                )
            ).all()
            retest_by_vul = {vid: (html or "") for vid, html in rows}

        pending: list[tuple[ReportSection, str]] = []
        # 纯数据快照：dry-run 需在 rollback 之后打印，而 rollback 会使会话内 ORM 实例过期
        # （再访问 s.id 等属性会抛 MissingGreenlet），故先把要展示 / 备份的值取出为普通 dict
        # （同时供备份文件复用）；约定见 scripts/_common.run() 的 docstring。
        records: list[dict] = []
        emptied: list[int] = []
        for s in sections:
            retest = retest_by_vul.get(s.vul_id or -1, "")
            new_html = strip_embedded_retest(s.content_html, retest)
            if new_html == s.content_html:
                continue
            if not new_html.strip():
                emptied.append(s.id)
            pending.append((s, new_html))
            records.append({
                "id": s.id,
                "report_id": s.report_id,
                "vul_id": s.vul_id,
                "before": s.content_html,
                "after": new_html,
            })

        if dry_run:
            await session.rollback()
            for row in records:
                print(
                    f"  [dry-run] 节 {row['id']}（报告 {row['report_id']} / 漏洞 {row['vul_id']}）"
                    f" {len(row['before'])} → {len(row['after'])} 字符"
                )
            print(f"[dry-run] 待清理 {len(records)} 个章节（未落库）")
        else:
            # 备份沿用原紧凑 JSON 格式（indent=None）；records 为空时 save_backup 返回 None，不打印路径
            backup_file = save_backup(records, "report_sections_retest", indent=None)
            backup_path = str(backup_file) if backup_file else ""
            for s, new_html in pending:
                s.content_html = new_html
            await session.commit()
            print(f"清理完成：已剥离 {len(pending)} 个章节的内嵌复测详情段")
            if backup_path:
                print(f"原值备份：{backup_path}")
        if emptied:
            print(f"⚠ 剥离后正文为空的章节（需人工复核）：{emptied}")


if __name__ == "__main__":
    # 统一入口：静默 SQLAlchemy 回显 + `--dry-run` 解析（审计 M-2）
    run(main, dry_run=dry_run_flag())
