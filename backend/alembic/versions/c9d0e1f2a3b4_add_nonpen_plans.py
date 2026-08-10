"""add nonpen plans table

非渗透计划模块（与测试计划平级）：主机/Web/基线扫描类测试的独立管理。

- 新增 nonpen_plans 表：工单ID与测试计划共享当日序号序列（ticket_seq / ticket_id_manual），
  items JSON 容器存储测试项状态与次数，testing_plan_id 标记联动来源（双向同步/级联删除）。
- testing_plans 新增 create_nonpen 列：测试计划表单「创建非渗透」勾选。

Revision ID: c9d0e1f2a3b4
Revises: b5c6d7e8f9a0
Create Date: 2026-08-10 00:00:00

"""
from alembic import op
import sqlalchemy as sa


revision = 'c9d0e1f2a3b4'
down_revision = 'b5c6d7e8f9a0'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'testing_plans',
        sa.Column('create_nonpen', sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_table(
        'nonpen_plans',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('plan_name', sa.String(length=128), nullable=False, server_default=''),
        sa.Column('system_name', sa.String(length=128), nullable=False, server_default=''),
        sa.Column('test_type', sa.String(length=64), nullable=False, server_default=''),
        sa.Column('department', sa.String(length=128), nullable=False, server_default=''),
        sa.Column('ticket_time', sa.String(length=32), nullable=False, server_default=''),
        sa.Column('receive_time', sa.String(length=32), nullable=False, server_default=''),
        sa.Column('ticket_seq', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('ticket_id_manual', sa.String(length=64), nullable=False, server_default=''),
        sa.Column('asset_ids', sa.JSON(), nullable=True),
        sa.Column('items', sa.JSON(), nullable=True),
        sa.Column('testing_plan_id', sa.Integer(), nullable=True),
        sa.Column('detail', sa.Text(), nullable=False, server_default=''),
        sa.Column('creator_id', sa.Integer(), nullable=True),
        sa.Column('create_time', sa.DateTime(), nullable=True),
        sa.Column('update_time', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['creator_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['testing_plan_id'], ['testing_plans.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_nonpen_plans_system_name'), 'nonpen_plans', ['system_name'], unique=False)
    op.create_index(op.f('ix_nonpen_plans_testing_plan_id'), 'nonpen_plans', ['testing_plan_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_nonpen_plans_testing_plan_id'), table_name='nonpen_plans')
    op.drop_index(op.f('ix_nonpen_plans_system_name'), table_name='nonpen_plans')
    op.drop_table('nonpen_plans')
    op.drop_column('testing_plans', 'create_nonpen')
