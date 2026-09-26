"""启用 pg_trgm 前后通配符索引（ROADMAP P0-4 的评估落地，显式运维动作）。

**评估结论**（2026-09-26，本机 PostgreSQL 16 + 10 万漏洞基准，见 `scripts/benchmark_lists.py --trgm`）：

| 指标 | 无 trgm 索引 | 建 GIN 三元组索引后 |
|---|---|---|
| `title ILIKE '%SQL注入%'` P95 | 43.5 ms | 5.3 ms |
| 执行计划 | Seq Scan + Filter | Bitmap Index Scan on ix_trgm_vulns_title |

**为什么不写成 Alembic 迁移**：`CREATE EXTENSION pg_trgm` 需要超级用户；写进迁移会在
「扩展不可用 / 权限不足」的库上直接让 `upgrade head` 失败（升级被一个性能优化阻断），
而全新库是 `create_all` 建的（不走迁移）会漏建索引——两条路径无法保持一致。故改为**显式、
可重入**的运维脚本：先报告可用性，再按结果决定是否建索引，最后打印 EXPLAIN 证据。

覆盖的列（与列表页 `%keyword%` 检索一一对应）：漏洞标题 / 资产名称 / 工单测试系统（两表）。

用法（生产/本地均可在容器或本机执行；幂等，可重复运行）：

    backend/.venv/Scripts/python -m scripts.enable_trgm_indexes --dry-run
    backend/.venv/Scripts/python -m scripts.enable_trgm_indexes

输出以 `RESULT` 开头，便于筛选（见 docs/SCRIPTS.md）。
"""
import argparse
import asyncio
import os
import sys
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND_DIR))
os.environ.setdefault("VP_DEBUG", "1")
os.environ.setdefault("VP_DISABLE_QUEUE", "1")
os.environ.setdefault("VP_DISABLE_REDIS", "1")

from sqlalchemy import text  # noqa: E402

from app.db import async_session_maker, engine  # noqa: E402

# (索引名, 表名, 列名)：与列表页模糊检索的热点列一一对应
TRGM_INDEXES = (
    ("ix_trgm_vulns_title", "vulns", "title"),
    ("ix_trgm_assets_name", "assets", "name"),
    ("ix_trgm_testing_plans_system_name", "testing_plans", "system_name"),
    ("ix_trgm_nonpen_plans_system_name", "nonpen_plans", "system_name"),
)


async def _trgm_available() -> bool:
    async with async_session_maker() as session:
        return bool((await session.execute(text(
            "SELECT count(*) FROM pg_available_extensions WHERE name = 'pg_trgm'"
        ))).scalar_one())


async def _ensure_extension() -> bool:
    try:
        async with async_session_maker() as session:
            await session.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
            await session.commit()
        return True
    except Exception as exc:  # noqa: BLE001  权限不足时给出结论，不抛栈
        print(f"RESULT extension=failed（需要超级用户或预装扩展）：{type(exc).__name__}")
        return False


async def _existing_indexes() -> set[str]:
    async with async_session_maker() as session:
        rows = (await session.execute(text(
            "SELECT indexname FROM pg_indexes WHERE indexname LIKE 'ix_trgm_%'"
        ))).all()
        return {r[0] for r in rows}


async def _create_indexes(dry_run: bool) -> int:
    before = await _existing_indexes()
    created = 0
    async with async_session_maker() as session:
        for name, table, column in TRGM_INDEXES:
            if name in before:
                print(f"RESULT index={name} status=exists")
                continue
            if dry_run:
                print(f"RESULT index={name} status=would-create on {table}({column})")
                continue
            await session.execute(text(
                f"CREATE INDEX IF NOT EXISTS {name} ON {table} USING gin ({column} gin_trgm_ops)"
            ))
            print(f"RESULT index={name} status=created on {table}({column})")
            created += 1
        if not dry_run:
            await session.commit()
    return created


async def main() -> None:
    parser = argparse.ArgumentParser(description="启用 pg_trgm 前后通配符索引（幂等）")
    parser.add_argument("--dry-run", action="store_true", help="只报告将执行的动作")
    args = parser.parse_args()

    if not await _trgm_available():
        print("RESULT trgm=unavailable（当前 PostgreSQL 未提供 pg_trgm，脚本无操作）")
        return
    print("RESULT trgm=available")
    if not args.dry_run and not await _ensure_extension():
        return
    created = await _create_indexes(args.dry_run)
    if not args.dry_run:
        async with async_session_maker() as session:
            for _name, table, _column in TRGM_INDEXES:
                await session.execute(text(f"ANALYZE {table}"))
            await session.commit()
        print(f"RESULT summary=created:{created} total:{len(TRGM_INDEXES)}")
        # 自证：打印一条代表性 EXPLAIN，确认索引可用（表为空时计划可能仍选顺序扫描）
        async with async_session_maker() as session:
            rows = (await session.execute(text(
                "EXPLAIN SELECT id FROM vulns WHERE title ILIKE '%SQL%' LIMIT 20"
            ))).all()
            for row in rows:
                print(f"RESULT   {row[0]}")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
