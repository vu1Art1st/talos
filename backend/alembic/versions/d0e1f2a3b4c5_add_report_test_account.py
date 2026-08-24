"""add test_account to reports

报告新增被测测试账号字段（导入报告时从「测试目标」表解析回填，
导出模板测试目标表第 5 行使用），供报告编辑页展示与编辑。

Revision ID: d0e1f2a3b4c5
Revises: b8c9d0e1f2a3
Create Date: 2026-08-25 00:00:00

"""
from alembic import op
import sqlalchemy as sa


revision = 'd0e1f2a3b4c5'
down_revision = 'b8c9d0e1f2a3'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('reports', sa.Column('test_account', sa.String(255), nullable=False, server_default=''))


def downgrade() -> None:
    op.drop_column('reports', 'test_account')
