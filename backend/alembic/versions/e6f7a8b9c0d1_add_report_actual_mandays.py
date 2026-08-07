"""add actual_mandays to reports

报告新增实际人天字段（自动计算 = 测试结束日期 - 开始日期），供报告编辑页展示：
发起复测自动生成的复测报告、以及普通报告的测试周期变更都会自动重算该值。

Revision ID: e6f7a8b9c0d1
Revises: d4e5f6a7b8c9
Create Date: 2026-08-07 00:00:00

"""
from alembic import op
import sqlalchemy as sa


revision = 'e6f7a8b9c0d1'
down_revision = 'd4e5f6a7b8c9'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('reports', sa.Column('actual_mandays', sa.Float(), nullable=False, server_default='0'))


def downgrade() -> None:
    op.drop_column('reports', 'actual_mandays')
