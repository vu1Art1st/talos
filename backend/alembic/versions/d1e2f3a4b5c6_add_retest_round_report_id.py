"""add retest round report id

复测轮次记录新增来源报告ID（testing_plan_retest_rounds.report_id）：
发起复测生成复测报告时关联对应轮次，删除该复测报告时回退对应轮次，
保证复测轮数与报告数据一致。

Revision ID: d1e2f3a4b5c6
Revises: c9d0e1f2a3b4
Create Date: 2026-08-13 00:00:00

"""
from alembic import op
import sqlalchemy as sa


revision = 'd1e2f3a4b5c6'
down_revision = 'c9d0e1f2a3b4'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'testing_plan_retest_rounds',
        sa.Column('report_id', sa.Integer(), nullable=True),
    )
    op.create_index(
        op.f('ix_testing_plan_retest_rounds_report_id'),
        'testing_plan_retest_rounds', ['report_id'], unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f('ix_testing_plan_retest_rounds_report_id'),
        table_name='testing_plan_retest_rounds',
    )
    op.drop_column('testing_plan_retest_rounds', 'report_id')
