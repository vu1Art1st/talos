"""cvss 3.1 vector and float score

CVSS 3.1 计算器（F4）：
- vulns.score 由 Integer 迁移为 Float（CVSS 基础评分 0.0-10.0，一位小数）；
- vulns / knowledge_entries 新增 cvss_vector 向量字符串列（空表示未评分）。

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-08-22 00:00:00

"""
from alembic import op
import sqlalchemy as sa


revision = 'f6a7b8c9d0e1'
down_revision = 'e5f6a7b8c9d0'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 评分列类型：Integer → Float（PostgreSQL 需显式 USING 转换；SQLite 由轻量迁移兜底）
    op.alter_column(
        'vulns', 'score',
        existing_type=sa.Integer(),
        type_=sa.Float(),
        postgresql_using='score::double precision',
    )
    op.add_column('vulns', sa.Column('cvss_vector', sa.String(length=255), nullable=False, server_default=''))
    op.add_column('knowledge_entries', sa.Column('cvss_vector', sa.String(length=255), nullable=False, server_default=''))


def downgrade() -> None:
    op.drop_column('knowledge_entries', 'cvss_vector')
    op.drop_column('vulns', 'cvss_vector')
    op.alter_column(
        'vulns', 'score',
        existing_type=sa.Float(),
        type_=sa.Integer(),
        postgresql_using='score::integer',
    )
