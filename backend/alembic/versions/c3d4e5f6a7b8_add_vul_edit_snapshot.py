"""add vul_edit_snapshot to reports

报告新增关联漏洞编辑时间快照（{vul_id: update_time}）：生成/保存报告时写入，
用于再次生成报告时的高度相似性判定（对比所选漏洞最后编辑时间是否变化）。

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-08-06 00:00:00

"""
from alembic import op
import sqlalchemy as sa


revision = 'c3d4e5f6a7b8'
down_revision = 'b2c3d4e5f6a7'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('reports', sa.Column('vul_edit_snapshot', sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column('reports', 'vul_edit_snapshot')
