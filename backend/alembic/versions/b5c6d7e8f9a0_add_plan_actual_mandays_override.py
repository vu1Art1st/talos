"""add actual_mandays_override to testing_plans

测试计划新增实际人天手动修正标志：有关联初测报告时系统按初测报告测试周期
自动计算实际人天；用户点击「修正」手动输入后置为 True，此后不再被自动计算
覆盖；点击「取消修正」置为 False 并恢复自动计算值。

Revision ID: b5c6d7e8f9a0
Revises: a3b4c5d6e7f8
Create Date: 2026-08-09 10:00:00

"""
from alembic import op
import sqlalchemy as sa


revision = 'b5c6d7e8f9a0'
down_revision = 'a3b4c5d6e7f8'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'testing_plans',
        sa.Column('actual_mandays_override', sa.Boolean(), nullable=False, server_default='false'),
    )


def downgrade() -> None:
    op.drop_column('testing_plans', 'actual_mandays_override')
