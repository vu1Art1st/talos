"""Alembic 迁移端到端守卫（2026-09-21 单轨化后新增）。

**为什么需要**：schema 演进自 2026-09-21 起只有 Alembic 一条轨道（SQLite 轻量迁移已删），
但测试建表走的是 lifespan 里的 `create_all`，`test_schema_consistency.py` 也只对迁移源码做
正则断言 —— 即**迁移脚本本身从未被执行过**，写坏的唯一暴露点是生产 `upgrade head`。
本文件把「真跑一遍迁移」纳入测试：在独立 schema 里 `upgrade head`，并断言迁移建出的
表/列与模型声明一致（覆盖「新增模型字段漏写迁移」这类最高频缺陷）。

**隔离口径**：通过 `VP_DB_SCHEMA` 把迁移的 search_path 固定到本文件的独立 schema
（`mig_<pid>`），既不触碰测试 schema，也不动 `public`；与并发运行互不干扰。
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest_asyncio
from sqlalchemy import text

_BACKEND_DIR = Path(__file__).resolve().parent.parent
_SCHEMA = f"mig_{os.getpid()}"
# 迁移链自建、不属于模型声明的表
_NON_MODEL_TABLES = {"alembic_version"}
# 已知「迁移建了、模型未映射」的惰性历史列白名单（登记为已知，不算不一致；其它漂移仍会失败）。
# P0-6（2026-09-26）已把历史欠账清空：testing_plans.create_nonpen 与 assets 的
# ports/services/middleware/database_type 五列各走一个独立迁移删除，并登记进
# tests/test_schema_consistency.DEPRECATED_COLUMNS。此处保留机制本身（空表），
# 供未来出现「暂不删列」的过渡期使用——新增条目必须在 DEPRECATED_COLUMNS 同步登记。
_LEGACY_UNMAPPED_COLUMNS: dict[str, set[str]] = {}


def _alembic(*args: str) -> subprocess.CompletedProcess[str]:
    """以子进程执行 alembic（与生产 scripts/migrate.py 同路径），search_path 指向本文件 schema。"""
    env = {**os.environ, "VP_DB_SCHEMA": _SCHEMA}
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=_BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
    )


def _assert_ok(result: subprocess.CompletedProcess[str], action: str) -> None:
    assert result.returncode == 0, (
        f"alembic {action} 失败（exit={result.returncode}）\n"
        f"--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}"
    )


async def _table_columns(schema: str) -> dict[str, set[str]]:
    """读取指定 schema 的「表 → 列集合」。"""
    from app.db import engine

    async with engine.connect() as conn:
        rows = (
            await conn.execute(
                text(
                    "SELECT table_name, column_name FROM information_schema.columns "
                    "WHERE table_schema = :schema"
                ),
                {"schema": schema},
            )
        ).all()
    out: dict[str, set[str]] = {}
    for table, column in rows:
        out.setdefault(table, set()).add(column)
    return out


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def mig_schema(client) -> str:
    """本次运行专属的迁移 schema（依赖 client 以确保事件循环与引擎已就绪）。"""
    from app.db import engine

    async with engine.begin() as conn:
        await conn.execute(text(f'DROP SCHEMA IF EXISTS "{_SCHEMA}" CASCADE'))
        await conn.execute(text(f'CREATE SCHEMA "{_SCHEMA}"'))
    yield _SCHEMA
    async with engine.begin() as conn:
        await conn.execute(text(f'DROP SCHEMA IF EXISTS "{_SCHEMA}" CASCADE'))


async def test_upgrade_head_builds_all_model_tables(mig_schema: str):
    """空 schema 上 upgrade head 必须成功，且建出的表/列与模型声明完全一致。

    「完全一致」是刻意的严格口径：多一列（模型删了、迁移没删）在 PostgreSQL 上会留下
    NOT NULL 僵尸列导致 INSERT 500；少一列（模型加了、迁移没写）会在生产直接报缺列。
    两种情况都必须在这里被拦住。
    """
    import app.models  # noqa: F401  注册全部模型
    from app.db import Base

    result = _alembic("upgrade", "head")
    _assert_ok(result, "upgrade head")

    actual = await _table_columns(mig_schema)
    for name in _NON_MODEL_TABLES:
        actual.pop(name, None)
    expected = {name: {c.name for c in table.columns} for name, table in Base.metadata.tables.items()}

    missing_tables = sorted(set(expected) - set(actual))
    extra_tables = sorted(set(actual) - set(expected))
    assert not missing_tables, f"迁移未建出的模型表：{missing_tables}（模型已声明但 Alembic 未建）"
    assert not extra_tables, f"迁移建出了模型未声明的表：{extra_tables}（模型已删但迁移未清理）"

    diffs: list[str] = []
    for table in sorted(expected):
        missing_cols = sorted(expected[table] - actual[table])
        extra_cols = sorted((actual[table] - expected[table]) - _LEGACY_UNMAPPED_COLUMNS.get(table, set()))
        if missing_cols:
            diffs.append(f"{table} 缺列（模型有、迁移无）：{missing_cols}")
        if extra_cols:
            diffs.append(f"{table} 多列（模型无、迁移有）：{extra_cols}")
    assert not diffs, "迁移与模型列不一致：\n  - " + "\n  - ".join(diffs)


async def test_downgrade_base_is_clean(mig_schema: str):
    """upgrade head → downgrade base 必须能回到空 schema（回滚路径可用）。"""
    _assert_ok(_alembic("upgrade", "head"), "upgrade head")
    _assert_ok(_alembic("downgrade", "base"), "downgrade base")

    remaining = {
        table: cols
        for table, cols in (await _table_columns(mig_schema)).items()
        if table not in _NON_MODEL_TABLES
    }
    assert not remaining, f"downgrade base 后仍残留表：{sorted(remaining)}（迁移 downgrade 分支不完整）"
