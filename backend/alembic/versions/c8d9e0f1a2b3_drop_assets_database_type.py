"""P0-6 遗留惰性列清理（4/5）：删除 assets.database_type

Revision ID: c8d9e0f1a2b3
Revises: b7c8d9e0f1a2
Create Date: 2026-09-26

删除前核查同 1/5（a5b6c7d8e9f0）：全仓无读写、升级前已备份、`downgrade` 精确恢复、
`DEPRECATED_COLUMNS` 双向登记。数据库信息现由 `databases`（JSON）承载。
"""
from alembic import op
import sqlalchemy as sa

revision = "c8d9e0f1a2b3"
down_revision = "b7c8d9e0f1a2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("assets", "database_type")


def downgrade() -> None:
    op.add_column(
        "assets",
        sa.Column("database_type", sa.String(length=128), nullable=False, server_default=""),
    )
