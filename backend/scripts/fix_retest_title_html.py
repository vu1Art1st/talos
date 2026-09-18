"""存量复测记录标题清理：转义标题中的 HTML 标签，并重算受影响漏洞的 `retest_html`。

背景（安全审计 TALOS-2026-005）：`vul_retest_records.title` 是纯文本字段（不受 `HtmlStr` 消毒
覆盖），但 `vul_service.sync_vul_retest_html` 会把它拼进 `vul.retest_html` 的 HTML 片段，
导致任意标签可被注入到该字段（既下发给前端渲染，又被报告导出链路当 HTML 解析）。代码已在聚合
入口统一 `html.escape`，本脚本清理存量：把标题里的原始标签转义，并按新口径重算 retest_html。

判定与幂等：只处理标题中含 `<` 或 `>` 的记录（转义后不再含原始尖括号，故重复执行结果一致）；
标题本身是普通文本，转义仅影响渲染语义（页面显示不变），不影响可读内容。

执行前把待改记录的原值备份到 `storage/backups/`（JSON），便于回滚复核。

用法（backend/ 目录，或容器内 /app）：
    python -m scripts.fix_retest_title_html            # 执行清理（自动备份）
    python -m scripts.fix_retest_title_html --dry-run  # 仅统计与打印，不落库
"""
import html as html_mod
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.db import async_session_maker  # noqa: E402
from app.models import Vul, VulRetestRecord  # noqa: E402
from app.services import vul_service  # noqa: E402
from scripts._common import dry_run_flag, run, save_backup  # noqa: E402

# 触发清理的字符：标题里出现原始尖括号即视为「含标签」，需转义
_TAG_CHARS = ("<", ">")


async def main(dry_run: bool = False) -> None:
    async with async_session_maker() as session:
        records = (
            await session.execute(select(VulRetestRecord).order_by(VulRetestRecord.id))
        ).scalars().all()
        targets = [
            r for r in records
            if (r.title or "").strip() and any(ch in r.title for ch in _TAG_CHARS)
        ]
        print(f"复测记录共 {len(records)} 条，其中标题含 HTML 标签 {len(targets)} 条")

        # 纯数据快照：dry-run 需在 rollback 之后打印/备份（约定见 scripts/_common.run()）
        snapshot: list[dict] = []
        pending: list[tuple[VulRetestRecord, str]] = []
        for r in targets:
            after = html_mod.escape(r.title.strip())
            snapshot.append({
                "id": r.id, "vul_id": r.vul_id, "before": r.title, "after": after,
            })
            pending.append((r, after))
            # 标记用 ASCII：Windows 控制台默认 GBK 无法编码 ⚠ 等符号，会在打印时抛 UnicodeEncodeError
            print(f"  [!] 记录 {r.id}（漏洞 {r.vul_id}）：{r.title!r} → {after!r}")

        vul_ids = sorted({r.vul_id for r, _ in pending if r.vul_id})
        if dry_run:
            await session.rollback()
            print(f"[dry-run] 待转义 {len(pending)} 条标题，待重算 {len(vul_ids)} 个漏洞的 retest_html（未落库）")
            return

        backup_file = save_backup(snapshot, "vul_retest_titles")
        for record, after in pending:
            record.title = after
        await session.flush()
        for vul_id in vul_ids:
            vul = await session.get(Vul, vul_id)
            if vul is not None:
                await vul_service.sync_vul_retest_html(session, vul)
        await session.commit()
        print(f"清理完成：已转义 {len(pending)} 条标题，重算 {len(vul_ids)} 个漏洞的 retest_html")
        if backup_file:
            print(f"原值备份：{backup_file}")


if __name__ == "__main__":
    run(main, dry_run=dry_run_flag())
