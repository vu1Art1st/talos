"""add import record level source

导入记录新增漏洞等级来源追溯字段（import_records）：
- level_source：detail（风险问题详情）/ summary（风险问题汇总）/ template（导入模板）/ default（中危兜底）
- level_summary_text / level_detail_text：两处原始等级文字，供导入预览弹窗提示不一致
- level_mismatch：汇总表与详情等级是否不一致，前端据此在确认入库前提醒

背景：报告作者常出现「风险问题详情」与「风险问题汇总」等级不一致（甚至两处漏洞集合
不同），旧实现只取汇总表、匹配失败时静默回落中危，导致漏洞等级被误判。

Revision ID: a4b5c6d7e8f9
Revises: d6e7f8a9b0c1
Create Date: 2026-09-10 00:00:00

"""
from alembic import op
import sqlalchemy as sa


revision = 'a4b5c6d7e8f9'
down_revision = 'd6e7f8a9b0c1'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'import_records',
        sa.Column('level_source', sa.String(length=16), nullable=False, server_default='default'),
    )
    op.add_column(
        'import_records',
        sa.Column('level_summary_text', sa.String(length=32), nullable=False, server_default=''),
    )
    op.add_column(
        'import_records',
        sa.Column('level_detail_text', sa.String(length=32), nullable=False, server_default=''),
    )
    op.add_column(
        'import_records',
        sa.Column('level_mismatch', sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column('import_records', 'level_mismatch')
    op.drop_column('import_records', 'level_detail_text')
    op.drop_column('import_records', 'level_summary_text')
    op.drop_column('import_records', 'level_source')
