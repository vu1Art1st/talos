"""add est_score_deduction to spring_actions

春耕行动新增预估扣分字段（最终扣分前一列），用于通报初期按漏洞等级预估的扣分数值，
与最终扣分（score_deduction）分开记录，便于比对申诉/复核前后的差异。

Revision ID: b3c4d5e6f7a8
Revises: d0e1f2a3b4c5
Create Date: 2026-08-30 00:00:00

"""
from alembic import op
import sqlalchemy as sa


revision = 'b3c4d5e6f7a8'
down_revision = 'd0e1f2a3b4c5'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('spring_actions', sa.Column('est_score_deduction', sa.Float(), nullable=False, server_default='0'))


def downgrade() -> None:
    op.drop_column('spring_actions', 'est_score_deduction')
