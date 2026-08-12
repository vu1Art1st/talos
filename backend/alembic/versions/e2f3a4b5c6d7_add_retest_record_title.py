"""add retest record title

复测记录新增自定义标题（vul_retest_records.title）：
用户可手动编辑复测记录标题以对应实际复测时间；标题为空时，
后端聚合（_sync_vul_retest_html）仍按创建日期自动生成「复测记录yymmdd」。

Revision ID: e2f3a4b5c6d7
Revises: d1e2f3a4b5c6
Create Date: 2026-08-13 00:00:00

"""
from alembic import op
import sqlalchemy as sa


revision = 'e2f3a4b5c6d7'
down_revision = 'd1e2f3a4b5c6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'vul_retest_records',
        sa.Column('title', sa.String(length=255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('vul_retest_records', 'title')
