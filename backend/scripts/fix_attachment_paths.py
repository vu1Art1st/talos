"""存量附件路径清理：置空春耕行动/远程检测记录中不符合上传白名单的附件路径。

背景（安全审计 TALOS-2026-001/002）：这两张表的附件路径历史上由客户端提交并直接落库，
下载/删除端点以 `settings.storage_path / 字段` 裸拼接，可越界读取/删除任意文件。代码已改为
「写入侧白名单 + 读取侧 storage 边界校验」，此后**存量非法路径只会解析为 404**，本脚本把这类
脏值置空，避免用户看到「附件打不开」的困惑，同时为安全事件留痕（脚本会把原值打印并备份）。

判定口径与 `app/core/storage.py::is_attachment_path` 完全一致：
    `uploads/spring_report/<32 位十六进制>.docx`（春耕行动原报告）
    `uploads/remote_appeal/<32 位十六进制>.<小写扩展名>`（远程检测申诉附件）

执行前把待改记录的原值备份到 `storage/backups/`（JSON），便于回滚复核。

用法（backend/ 目录，或容器内 /app）：
    python -m scripts.fix_attachment_paths            # 执行置空（自动备份）
    python -m scripts.fix_attachment_paths --dry-run  # 仅统计与打印，不落库
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.core.storage import is_attachment_path  # noqa: E402
from app.db import async_session_maker  # noqa: E402
from app.models import RemoteTesting, SpringAction  # noqa: E402
from scripts._common import dry_run_flag, run, save_backup  # noqa: E402

# (表名, 字段说明, 子目录) 三元组：与路由层 require_attachment_path 的 subdir 参数一致
TARGETS = (
    (SpringAction, "report_file_path", "spring_report", "春耕行动-原始报告附件"),
    (RemoteTesting, "appeal_file_path", "remote_appeal", "远程检测-申诉报告附件"),
)


async def main(dry_run: bool = False) -> None:
    async with async_session_maker() as session:
        records: list[dict] = []
        pending: list[tuple[object, str]] = []
        for model, field, subdir, label in TARGETS:
            rows = (
                await session.execute(select(model).where(getattr(model, field) != ""))
            ).scalars().all()
            bad = [r for r in rows if not is_attachment_path(getattr(r, field), subdir=subdir)]
            print(f"{label}：共 {len(rows)} 条带路径，其中不符合白名单 {len(bad)} 条")
            for r in bad:
                # 纯数据快照：dry-run 需在 rollback 之后打印，rollback 会使会话内 ORM 实例过期
                # （再访问属性会抛 MissingGreenlet），故先取成普通 dict；约定见 scripts/_common.run()
                value = getattr(r, field)
                records.append({
                    "table": model.__tablename__, "id": r.id, "field": field, "value": value,
                })
                pending.append((r, value))
                # 标记用 ASCII：Windows 控制台默认 GBK 无法编码 ⚠ 等符号，会在打印时抛 UnicodeEncodeError
                print(f"  [!] {model.__tablename__} id={r.id} {field}={value!r}")

        if dry_run:
            await session.rollback()
            print(f"[dry-run] 待置空 {len(records)} 条（未落库）")
            return

        backup_file = save_backup(records, "attachment_paths")
        for row, _value in pending:
            for model, field, _subdir, _label in TARGETS:
                if isinstance(row, model):
                    setattr(row, field, "")
                    break
        await session.commit()
        print(f"清理完成：已置空 {len(pending)} 条非法附件路径")
        if backup_file:
            print(f"原值备份：{backup_file}")
        if records:
            print("[!] 如属未授权访问痕迹，请按安全整改单处置（轮换 VP_SECRET_KEY 并复核账号）")


if __name__ == "__main__":
    run(main, dry_run=dry_run_flag())
