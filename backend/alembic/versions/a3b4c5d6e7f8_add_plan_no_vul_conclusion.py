"""add no_vul_conclusion to testing_plans

测试计划新增无漏洞闭环测试结论字段：测试完成且确认未发现安全漏洞时（状态流转为
「测试通过」）记录测试结论，供无漏洞报告与后续追溯使用；计划重开时保留该值。

Revision ID: a3b4c5d6e7f8
Revises: f8a9b0c1d2e3
Create Date: 2026-08-07 15:00:00

"""
from alembic import op
import sqlalchemy as sa


revision = 'a3b4c5d6e7f8'
down_revision = 'f8a9b0c1d2e3'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'testing_plans',
        sa.Column('no_vul_conclusion', sa.Text(), nullable=False, server_default=''),
    )


def downgrade() -> None:
    op.drop_column('testing_plans', 'no_vul_conclusion')
