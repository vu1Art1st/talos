"""add report_snapshot to export_jobs

导出任务新增报告内容指纹（{revision, update_time, vul_edit_snapshot}）：创建任务时
记录导出时的报告状态，供再次导出前的重复导出判断（内容一致则提示确认）。

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-08-06 00:00:00

"""
from alembic import op
import sqlalchemy as sa


revision = 'd4e5f6a7b8c9'
down_revision = 'c3d4e5f6a7b8'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('export_jobs', sa.Column('report_snapshot', sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column('export_jobs', 'report_snapshot')
