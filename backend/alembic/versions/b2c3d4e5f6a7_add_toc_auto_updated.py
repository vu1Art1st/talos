"""add toc_auto_updated to export_jobs

导出任务新增 toc_auto_updated 标记：记录该次导出是否已由 LibreOffice
宏自动更新目录域。False 时前端在下载后提示用户打开 Word 手动更新（F9）。

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-08-05 00:00:00

"""
from alembic import op
import sqlalchemy as sa


revision = 'b2c3d4e5f6a7'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'export_jobs',
        sa.Column('toc_auto_updated', sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column('export_jobs', 'toc_auto_updated')
