"""add report file to spring_actions

春耕行动新增原始报告附件三字段（文件名/存储路径/大小），支持上传原始报告 Word 文档：
解析回填系统名称/年度并导入漏洞草稿，附件本身留档可下载。

Revision ID: d6e7f8a9b0c1
Revises: c5d6e7f8a9b0
Create Date: 2026-08-30 00:00:00

"""
from alembic import op
import sqlalchemy as sa


revision = 'd6e7f8a9b0c1'
down_revision = 'c5d6e7f8a9b0'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('spring_actions', sa.Column('report_file_name', sa.String(length=255), nullable=False, server_default=''))
    op.add_column('spring_actions', sa.Column('report_file_path', sa.String(length=512), nullable=False, server_default=''))
    op.add_column('spring_actions', sa.Column('report_file_size', sa.Integer(), nullable=False, server_default='0'))


def downgrade() -> None:
    op.drop_column('spring_actions', 'report_file_size')
    op.drop_column('spring_actions', 'report_file_path')
    op.drop_column('spring_actions', 'report_file_name')
