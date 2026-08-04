"""生产数据库结构迁移（幂等）：以 Alembic 为准演进 PostgreSQL 表结构。见 docs/DEPLOY.md。

用法（容器内 /app 目录，或 docker compose run --rm api python -m scripts.migrate）：
    python -m scripts.migrate

决策逻辑（自动纳管 create_all 建的旧库，避免与 Alembic 冲突）：
- 已存在 alembic_version 表           → alembic upgrade head（应用增量迁移）
- 无 alembic_version 但业务表已存在   → alembic stamp head（旧库一次性纳管，schema 已由 create_all 建为最新）
- 全新空库                           → alembic upgrade head（由迁移脚本从基线建全表）

注意：为使「无版本表 + 业务表已存在 → stamp head」成立，每次发布后都必须执行本脚本，
否则跨多个版本时旧库可能被误判纳管到 head 而漏掉中间的 ALTER 迁移。
"""
import asyncio
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import inspect  # noqa: E402

from app.db import engine  # noqa: E402


async def _table_names() -> set[str]:
    async with engine.connect() as conn:
        return await conn.run_sync(lambda sync_conn: set(inspect(sync_conn).get_table_names()))


def _alembic(*args: str) -> None:
    print(f"→ alembic {' '.join(args)}", flush=True)
    subprocess.run([sys.executable, "-m", "alembic", *args], check=True)


async def main() -> None:
    names = await _table_names()
    await engine.dispose()

    if "alembic_version" in names:
        _alembic("upgrade", "head")
    elif "users" in names:
        # 旧库由 create_all 建表、schema 已是当前模型最新态：纳管到 head，不重复建表
        _alembic("stamp", "head")
    else:
        _alembic("upgrade", "head")


if __name__ == "__main__":
    asyncio.run(main())
