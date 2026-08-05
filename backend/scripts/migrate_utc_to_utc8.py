"""存量数据时区迁移：将历史 naive UTC 时间整体 +8 小时换算为北京时间（UTC+8）。

背景：旧版本统一以 UTC 存储时间（timeutil.utcnow），页面按原值展示，东八区用户看到
的时间比实际晚 8 小时。本次将系统标准时区调整为 UTC+8（Asia/Shanghai），此后新写入
的数据均为北京时间。

仅需在部署新版本前对存量库执行一次（建议先备份，见 docs/DEPLOY.md）：
    cd backend
    python -m scripts.migrate_utc_to_utc8            # 正式迁移
    python -m scripts.migrate_utc_to_utc8 --dry-run  # 仅预览受影响的行数

说明：
- 对所有 DateTime 列执行 +8h；
- 纯日期字符串列（如 reports.test_start/test_end、testing_plans 各 *_time）无法精确
  换算，不做处理，请人工核对；
- 全新空库 / 新部署无需执行本脚本。
"""
import asyncio
import sys
from datetime import datetime

import app.models  # noqa: F401  确保全部模型注册，Base.metadata 完整
from sqlalchemy import text

from app.core.config import settings
from app.db import Base


async def migrate(dry_run: bool = False) -> int:
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(settings.DATABASE_URL)
    affected = 0
    try:
        async with engine.connect() as conn:
            trans = await conn.begin()
            try:
                is_sqlite = engine.dialect.name == "sqlite"
                for table in Base.metadata.sorted_tables:
                    for column in table.columns:
                        # JSON 等类型不提供 python_type（或抛 NotImplementedError），跳过
                        try:
                            py_type = column.type.python_type
                        except (NotImplementedError, AttributeError):
                            continue
                        if py_type is not datetime:
                            continue
                        table_name = table.name
                        col_name = column.name
                        if is_sqlite:
                            expr = f'"{col_name}" = datetime("{col_name}", \'+8 hours\')'
                        else:
                            expr = f'"{col_name}" = "{col_name}" + INTERVAL \'8 hours\''
                        result = await conn.execute(text(
                            f'UPDATE "{table_name}" SET {expr} WHERE "{col_name}" IS NOT NULL'
                        ))
                        n = result.rowcount or 0
                        if n:
                            print(f"{table_name}.{col_name}: +8h 更新 {n} 行")
                            affected += n
                if dry_run:
                    print("[dry-run] 未提交任何变更（已回滚）")
                    await trans.rollback()
                else:
                    await trans.commit()
                    print(f"迁移完成，共更新 {affected} 行。")
            except Exception:
                await trans.rollback()
                raise
    finally:
        await engine.dispose()
    return affected


def main() -> None:
    dry_run = "--dry-run" in sys.argv[1:]
    asyncio.run(migrate(dry_run=dry_run))


if __name__ == "__main__":
    main()
