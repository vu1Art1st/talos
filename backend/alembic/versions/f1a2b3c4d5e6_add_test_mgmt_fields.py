"""add test management fields

新增测试计划增强字段（工单时间/工单序号/计划名称/关联资产）、
组织成员表（group_members）、漏洞类型字典表（vuln_types）、资产系统类型字段。

Revision ID: f1a2b3c4d5e6
Revises: e9054a84d196
Create Date: 2026-08-03 00:00:00

"""
from alembic import op
import sqlalchemy as sa


revision = 'f1a2b3c4d5e6'
down_revision = 'e9054a84d196'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 组织成员表：取代 Group 表 owner_* 单字段，支持一个组织多名成员
    op.create_table(
        'group_members',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('group_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=64), nullable=False),
        sa.Column('phone', sa.String(length=32), nullable=False),
        sa.Column('email', sa.String(length=128), nullable=False),
        sa.Column('create_time', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['group_id'], ['groups.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_group_members_group_id', 'group_members', ['group_id'], unique=False)

    # 漏洞类型字典表：内置类型 is_builtin=True，自定义类型支持新增
    op.create_table(
        'vuln_types',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('code', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=64), nullable=False),
        sa.Column('sort', sa.Integer(), nullable=False),
        sa.Column('is_builtin', sa.Boolean(), nullable=False),
        sa.Column('create_time', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('code', name='uq_vuln_type_code'),
    )
    op.create_index('ix_vuln_types_code', 'vuln_types', ['code'], unique=False)

    # 测试计划增强字段
    op.add_column('testing_plans', sa.Column('ticket_time', sa.String(length=32), nullable=False, server_default=''))
    op.add_column('testing_plans', sa.Column('ticket_seq', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('testing_plans', sa.Column('plan_name', sa.String(length=128), nullable=False, server_default=''))
    op.add_column('testing_plans', sa.Column('asset_ids', sa.JSON(), nullable=True))
    # 存量行为 NULL 时回填空数组，避免 TestingPlanOut 序列化失败
    op.execute("UPDATE testing_plans SET asset_ids = '[]' WHERE asset_ids IS NULL")

    # 资产系统类型字段
    op.add_column('assets', sa.Column('system_type', sa.String(length=64), nullable=False, server_default=''))


def downgrade() -> None:
    op.drop_column('assets', 'system_type')
    op.drop_column('testing_plans', 'asset_ids')
    op.drop_column('testing_plans', 'plan_name')
    op.drop_column('testing_plans', 'ticket_seq')
    op.drop_column('testing_plans', 'ticket_time')
    op.drop_index('ix_vuln_types_code', table_name='vuln_types')
    op.drop_table('vuln_types')
    op.drop_index('ix_group_members_group_id', table_name='group_members')
    op.drop_table('group_members')
