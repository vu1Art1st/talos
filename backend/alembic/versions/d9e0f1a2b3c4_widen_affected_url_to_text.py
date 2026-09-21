"""widen affected_url to text

影响URL 支持一漏洞多条 URL（前端按换行分隔写入单字段，见 `schemas.common.normalize_affected_url`）。
原 `varchar(512)` 在录入约 20 条 URL 时即溢出，PostgreSQL 抛 StringDataRightTruncation
（SQLSTATE 22001）导致提交 500。此处把两列统一放宽为 `TEXT`：

- `vulns.affected_url`（模型 app/models/business.py）
- `import_records.affected_url`（模型 app/models/imports.py）

幂等：仅当当前列类型不是 TEXT 时才改（重复执行为空操作）。
（历史：曾跳过 SQLite —— 其 VARCHAR 仅为类型亲和、不强制长度且不支持 ALTER COLUMN TYPE，
开发库当时由 app/db.py 轻量迁移兜底；该机制已于 2026-09-21 移除。）

**回滚风险（重要）**：downgrade 把列改回 varchar(512) 时，若库中已存在超过 512 字符的数据，
PostgreSQL 会直接拒绝该 DDL。紧急回滚请优先只回退应用代码、保留 TEXT 列（TEXT 本身无害）。

Revision ID: d9e0f1a2b3c4
Revises: c7d8e9f0a1b2
Create Date: 2026-09-18 00:00:00

"""
from alembic import op
import sqlalchemy as sa


revision = 'd9e0f1a2b3c4'
down_revision = 'c7d8e9f0a1b2'
branch_labels = None
depends_on = None


def _is_text(table: str, column: str) -> bool:
    """当前列是否已是 TEXT（幂等判定）。"""
    inspector = sa.inspect(op.get_bind())
    for col in inspector.get_columns(table):
        if col["name"] == column:
            return type(col["type"]).__name__.lower() == "text"
    return False


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        # 非 PostgreSQL 方言直接跳过（历史遗留的 SQLite 兼容分支；长度约束只存在于 PostgreSQL）
        return
    if not _is_text("vulns", "affected_url"):
        op.alter_column(
            "vulns", "affected_url",
            existing_type=sa.String(length=512),
            type_=sa.Text(),
            existing_nullable=False,
        )
    if not _is_text("import_records", "affected_url"):
        op.alter_column(
            "import_records", "affected_url",
            existing_type=sa.String(length=512),
            type_=sa.Text(),
            existing_nullable=False,
        )


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    # 若库中已存在超过 512 字符的数据，PostgreSQL 会拒绝此 DDL（见模块 docstring 回滚说明）
    if _is_text("vulns", "affected_url"):
        op.alter_column(
            "vulns", "affected_url",
            existing_type=sa.Text(),
            type_=sa.String(length=512),
            existing_nullable=False,
        )
    if _is_text("import_records", "affected_url"):
        op.alter_column(
            "import_records", "affected_url",
            existing_type=sa.Text(),
            type_=sa.String(length=512),
            existing_nullable=False,
        )
