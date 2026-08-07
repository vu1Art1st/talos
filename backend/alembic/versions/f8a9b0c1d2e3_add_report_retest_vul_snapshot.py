"""add retest_vul_snapshot to reports

报告新增发起复测时关联漏洞状态快照（{vul_id: {status, retest_html, retest_json}}）：
再次发起复测时对比当前漏洞状态与快照，若未更新则阻止生成新复测报告并提示。

Revision ID: f8a9b0c1d2e3
Revises: f7a8b9c0d1e2
Create Date: 2026-08-07 00:00:00

"""
from alembic import op
import sqlalchemy as sa


revision = 'f8a9b0c1d2e3'
down_revision = 'f7a8b9c0d1e2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('reports', sa.Column('retest_vul_snapshot', sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column('reports', 'retest_vul_snapshot')
