"""add asset_reason to spring_actions

春耕行动新增资产认定原因字段（申诉结果前一列），记录对应系统资产归属的认定依据，
与申诉结果（appeal_success）分开记录。

Revision ID: c5d6e7f8a9b0
Revises: b3c4d5e6f7a8
Create Date: 2026-08-30 00:00:00

"""
from alembic import op
import sqlalchemy as sa


revision = 'c5d6e7f8a9b0'
down_revision = 'b3c4d5e6f7a8'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('spring_actions', sa.Column('asset_reason', sa.String(length=255), nullable=False, server_default=''))


def downgrade() -> None:
    op.drop_column('spring_actions', 'asset_reason')
