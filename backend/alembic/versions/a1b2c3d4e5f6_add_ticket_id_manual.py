"""add manual ticket id field

测试计划新增手动工单ID字段（ticket_id_manual），
允许用户手动指定工单ID，留空时仍按需求接收日期自动生成。

Revision ID: a1b2c3d4e5f6
Revises: f1a2b3c4d5e6
Create Date: 2026-08-04 00:00:00

"""
from alembic import op
import sqlalchemy as sa


revision = 'a1b2c3d4e5f6'
down_revision = 'f1a2b3c4d5e6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'testing_plans',
        sa.Column('ticket_id_manual', sa.String(length=64), nullable=False, server_default=''),
    )


def downgrade() -> None:
    op.drop_column('testing_plans', 'ticket_id_manual')
