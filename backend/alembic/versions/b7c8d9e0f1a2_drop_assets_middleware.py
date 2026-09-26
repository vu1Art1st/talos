"""P0-6 遗留惰性列清理（3/5）：删除 assets.middleware

Revision ID: b7c8d9e0f1a2
Revises: b6c7d8e9f0a1
Create Date: 2026-09-26

删除前核查同 1/5（a5b6c7d8e9f0）：全仓无读写、升级前已备份、`downgrade` 精确恢复、
`DEPRECATED_COLUMNS` 双向登记。中间件现由 `middlewares`（JSON）承载。
"""
from alembic import op
import sqlalchemy as sa

revision = "b7c8d9e0f1a2"
down_revision = "b6c7d8e9f0a1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("assets", "middleware")


def downgrade() -> None:
    op.add_column(
        "assets",
        sa.Column("middleware", sa.String(length=128), nullable=False, server_default=""),
    )
