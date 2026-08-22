"""operation logs, notification channels, personal access tokens

审计/通知/开放 API 三张新表（F7 / F3 / F6）：
- operation_logs：登录与敏感操作审计日志（用户删除后 user_id 置空，冗余 username 保留可读）；
- notification_channels：企业微信/钉钉 webhook 与邮件通知渠道配置；
- personal_access_tokens：个人访问令牌（只存 sha256，用户删除级联删除）。

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-08-22 00:00:00

"""
from alembic import op
import sqlalchemy as sa


revision = 'a7b8c9d0e1f2'
down_revision = 'f6a7b8c9d0e1'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'operation_logs',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('username', sa.String(length=64), nullable=False, server_default=''),
        sa.Column('action', sa.String(length=64), nullable=False, server_default=''),
        sa.Column('detail', sa.Text(), nullable=False, server_default=''),
        sa.Column('ip', sa.String(length=64), nullable=False, server_default=''),
        sa.Column('user_agent', sa.String(length=256), nullable=False, server_default=''),
        sa.Column('create_time', sa.DateTime(), nullable=True),
    )
    op.create_index(op.f('ix_operation_logs_user_id'), 'operation_logs', ['user_id'])
    op.create_index(op.f('ix_operation_logs_username'), 'operation_logs', ['username'])
    op.create_index(op.f('ix_operation_logs_action'), 'operation_logs', ['action'])
    op.create_index(op.f('ix_operation_logs_create_time'), 'operation_logs', ['create_time'])

    op.create_table(
        'notification_channels',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(length=64), nullable=False),
        sa.Column('type', sa.String(length=16), nullable=False),
        sa.Column('config', sa.JSON(), nullable=True),
        sa.Column('events', sa.JSON(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('create_time', sa.DateTime(), nullable=True),
        sa.Column('update_time', sa.DateTime(), nullable=True),
    )

    op.create_table(
        'personal_access_tokens',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(length=64), nullable=False, server_default=''),
        sa.Column('token_hash', sa.String(length=64), nullable=False),
        sa.Column('prefix', sa.String(length=16), nullable=False, server_default=''),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('last_used_at', sa.DateTime(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('create_time', sa.DateTime(), nullable=True),
    )
    op.create_index(op.f('ix_personal_access_tokens_user_id'), 'personal_access_tokens', ['user_id'])
    op.create_index(op.f('ix_personal_access_tokens_token_hash'), 'personal_access_tokens', ['token_hash'], unique=True)


def downgrade() -> None:
    op.drop_index(op.f('ix_personal_access_tokens_token_hash'), table_name='personal_access_tokens')
    op.drop_index(op.f('ix_personal_access_tokens_user_id'), table_name='personal_access_tokens')
    op.drop_table('personal_access_tokens')
    op.drop_table('notification_channels')
    op.drop_index(op.f('ix_operation_logs_create_time'), table_name='operation_logs')
    op.drop_index(op.f('ix_operation_logs_action'), table_name='operation_logs')
    op.drop_index(op.f('ix_operation_logs_username'), table_name='operation_logs')
    op.drop_index(op.f('ix_operation_logs_user_id'), table_name='operation_logs')
    op.drop_table('operation_logs')
