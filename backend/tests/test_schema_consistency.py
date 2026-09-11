"""模型 / 迁移结构一致性守卫。

PostgreSQL 走 Alembic 演进、SQLite 开发库走 db.py 的轻量迁移，两条轨道一旦不同步，就会在
PostgreSQL 里留下「模型已删、库中仍是 NOT NULL 且无默认值」的僵尸列，任何 INSERT 直接 500
（remote_testings.appeal_success 即此坑：模型已改用 appeal_status，迁移 e5f6a7b8c9d0 漏删旧列，
由 b4c5d6e7f8a9 补删）。

约定：模型里重命名 / 删除的列必须登记到 DEPRECATED_COLUMNS，并由两条轨道同时清理。
"""
import re
from pathlib import Path

from app import models  # noqa: F401  确保全部模型注册到 Base.metadata
from app.db import Base

_BACKEND_DIR = Path(__file__).resolve().parent.parent
_MIGRATIONS_DIR = _BACKEND_DIR / "alembic" / "versions"
_LIGHTWEIGHT_MIGRATION = _BACKEND_DIR / "app" / "db.py"

# 表名 -> 已从模型移除的历史列名（新增重命名时在此登记）
DEPRECATED_COLUMNS = {
    "remote_testings": {"appeal_success", "title", "test_time", "appeal_report_id"},
}


def test_deprecated_columns_absent_from_models():
    """模型不得再映射已废弃列（映射了就是口径没改干净）。"""
    mapped = {(t.name, c.name) for t in Base.metadata.tables.values() for c in t.columns}
    for table, columns in DEPRECATED_COLUMNS.items():
        for column in columns:
            assert (table, column) not in mapped, f"{table}.{column} 仍被模型映射"


def test_deprecated_columns_dropped_by_alembic():
    """Alembic 迁移必须显式删除废弃列，否则 PostgreSQL 会残留 NOT NULL 僵尸列。"""
    source = "\n".join(p.read_text(encoding="utf-8") for p in _MIGRATIONS_DIR.glob("*.py"))
    for table, columns in DEPRECATED_COLUMNS.items():
        for column in columns:
            pattern = rf"drop_column\(\s*['\"]{table}['\"]\s*,\s*['\"]{column}['\"]"
            assert re.search(pattern, source), f"{table}.{column} 未在任何 Alembic 迁移中被删除"


def test_lightweight_migration_drops_legacy_appeal_success():
    """SQLite 开发库不经 Alembic，轻量迁移同样要清理遗留列。

    注：title / test_time / appeal_report_id 由「重建表」分支整体清理（非字面 DROP COLUMN），
    而 appeal_success 与它们同批重建后仍可能残留在不走重建的旧库，故单独断言其显式删除。
    """
    source = _LIGHTWEIGHT_MIGRATION.read_text(encoding="utf-8")
    assert "DROP COLUMN appeal_success" in source
