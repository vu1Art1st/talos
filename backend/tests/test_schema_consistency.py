"""模型 / 迁移结构一致性守卫（PostgreSQL 单轨）。

自 2026-09-21 起 schema 演进只有**一条轨道：Alembic**（SQLite 开发库专用的 `app/db.py`
轻量迁移已随 SQLite 收口删除）。本文件固化的核心风险是「模型已删列、而迁移漏删」——
PostgreSQL 会残留「NOT NULL 且无默认值」的僵尸列，任何 INSERT 直接 500
（remote_testings.appeal_success 即此坑：模型已改用 appeal_status，迁移 e5f6a7b8c9d0
漏删旧列，由 b4c5d6e7f8a9 补删）。

约定：模型里重命名 / 删除的列必须登记到 DEPRECATED_COLUMNS，并由 Alembic 迁移清理。
"""
import re
from pathlib import Path

from app import models  # noqa: F401  确保全部模型注册到 Base.metadata
from app.db import Base

_BACKEND_DIR = Path(__file__).resolve().parent.parent
_MIGRATIONS_DIR = _BACKEND_DIR / "alembic" / "versions"

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


# 影响URL 必须为不限长类型：定长列（曾为 varchar(512)）在录入约 20 条 URL 时溢出，
# PostgreSQL 抛 StringDataRightTruncation 导致 500（2026-09-18 修复）。
_URL_TEXT_COLUMNS = (("vulns", "affected_url"), ("import_records", "affected_url"))


def test_affected_url_columns_are_text_in_models():
    """模型侧 affected_url 不得回退为定长 String（长度校验改由 schema 层承担）。"""
    from sqlalchemy import Text

    tables = Base.metadata.tables
    for table, column in _URL_TEXT_COLUMNS:
        col = tables[table].columns[column]
        assert isinstance(col.type, Text), f"{table}.{column} 应为 Text，当前为 {col.type!r}"


def test_affected_url_widened_by_alembic():
    """affected_url 必须有 Alembic 迁移改为 TEXT（定长列约 20 条 URL 即溢出，PG 直接 500）。"""
    source = "\n".join(p.read_text(encoding="utf-8") for p in _MIGRATIONS_DIR.glob("*.py"))
    for table, column in _URL_TEXT_COLUMNS:
        pattern = (
            rf"alter_column\(\s*['\"]{table}['\"]\s*,\s*['\"]{column}['\"]"
            rf"[\s\S]{{0,400}}?type_=sa\.Text\(\)"
        )
        assert re.search(pattern, source), f"{table}.{column} 未在任何 Alembic 迁移中被改为 Text"


def test_affected_url_not_truncated_by_docx_parser():
    """Word 解析器不得对 affected_url 做定长截断，否则多 URL 文本会被静默砍到 512 字符。"""
    parser_source = (_BACKEND_DIR / "app" / "services" / "docx_parser.py").read_text(encoding="utf-8")
    truncations = re.findall(r'record\["affected_url"\][^\n]*\[:\d+\]', parser_source)
    assert not truncations, f"docx_parser 仍在截断 affected_url：{truncations}"


# 复测轮次「源报告」外键（2026-09-19）：报告维度复测状态依赖它，缺列会让发起复测直接 500，
# 因此新增列必须落到 Alembic 迁移（单轨后无第二条兜底路径）。
def test_retest_round_src_report_column_in_alembic():
    from app.models import TestingPlanRetestRound

    assert "src_report_id" in TestingPlanRetestRound.__table__.columns, "模型缺少 src_report_id"

    migrations = "\n".join(p.read_text(encoding="utf-8") for p in _MIGRATIONS_DIR.glob("*.py"))
    assert re.search(
        r"add_column\(\s*['\"]testing_plan_retest_rounds['\"][\s\S]{0,200}?src_report_id", migrations,
    ), "Alembic 未新增 testing_plan_retest_rounds.src_report_id"


# ---------- SQLite 收口回归守卫（2026-09-21）----------
# 以下两条锁定「单数据库栈」决策：应用代码不得再引入 SQLite 驱动，配置默认 DSN 不得回退。
# 之所以要固化：该迁移的动因正是 SQLite 与 PG 的方言差异已造成 7 次线上/发布前缺陷。


def test_no_sqlite_driver_imports_in_app():
    """应用代码不得再引入 SQLite 驱动（收口后唯一驱动为 asyncpg）。"""
    offenders = sorted(
        str(p.relative_to(_BACKEND_DIR))
        for p in (_BACKEND_DIR / "app").rglob("*.py")
        if re.search(r"\b(aiosqlite|sqlite3)\b", p.read_text(encoding="utf-8"))
    )
    assert not offenders, f"app/ 下仍引用 SQLite 驱动：{offenders}"


def test_default_database_url_is_postgresql():
    """配置默认 DSN 必须为 PostgreSQL：回退成 SQLite 默认值会让新环境静默跑错方言。"""
    from app.core.config import Settings

    default = Settings.model_fields["DATABASE_URL"].default
    assert isinstance(default, str) and default.startswith("postgresql"), f"默认 DSN 已回退：{default!r}"
