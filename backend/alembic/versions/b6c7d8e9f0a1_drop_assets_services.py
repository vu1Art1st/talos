"""P0-6 遗留惰性列清理（2/5）：删除 assets.services

Revision ID: b6c7d8e9f0a1
Revises: a5b6c7d8e9f0
Create Date: 2026-09-26

删除前核查同 1/5（a5b6c7d8e9f0）：全仓无读写、升级前已备份、`downgrade` 精确恢复、
`DEPRECATED_COLUMNS` 双向登记。服务信息现由 `port_services` / `middlewares` 承载。
"""
from alembic import op
import sqlalchemy as sa

revision = "b6c7d8e9f0a1"
down_revision = "a5b6c7d8e9f0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("assets", "services")


def downgrade() -> None:
    op.add_column(
        "assets",
        sa.Column("services", sa.String(length=255), nullable=False, server_default=""),
    )
