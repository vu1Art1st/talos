"""refactor vuln source and remote testing

漏洞来源口径重构（vulns.source 旧值废弃并重置为 0）+ 远程检测表单项按通报口径重构：
- remote_testings 新增：通报时间/被通报单位/是否外部项目/漏洞名称/漏洞类型/申诉方式/申诉报告附件字段；
- 申诉状态（appeal_status）替换原「申诉成功」布尔，存量由布尔回填；
- 废弃列：title / test_time / appeal_report_id（申诉报告不再关联报告中心，改为附件上传）；
  其中 appeal_report_id 带外键约束、title 带索引，需先 drop 约束/索引再 drop 列；
- 系统名称新增索引（ix_remote_testings_system_name）替换原标题索引（ix_remote_testings_title）；
- vulns.source：旧口径（安全部/SRC/众测/Word导入等）与新口径同码不同义，一次性全部重置为 0。

Revision ID: e5f6a7b8c9d0
Revises: e2f3a4b5c6d7
Create Date: 2026-08-14 00:00:00

"""
from alembic import op
import sqlalchemy as sa


revision = 'e5f6a7b8c9d0'
down_revision = 'e2f3a4b5c6d7'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ---- 远程检测：新增通报口径字段 ----
    op.add_column('remote_testings', sa.Column('notice_time', sa.String(length=32), nullable=False, server_default=''))
    op.add_column('remote_testings', sa.Column('notified_unit', sa.String(length=128), nullable=False, server_default=''))
    op.add_column('remote_testings', sa.Column('is_external', sa.Boolean(), nullable=False, server_default=sa.text('false')))
    op.add_column('remote_testings', sa.Column('vuln_name', sa.String(length=255), nullable=False, server_default=''))
    op.add_column('remote_testings', sa.Column('vuln_type', sa.String(length=64), nullable=False, server_default=''))
    op.add_column('remote_testings', sa.Column('appeal_method', sa.String(length=64), nullable=False, server_default=''))
    op.add_column('remote_testings', sa.Column('appeal_file_name', sa.String(length=255), nullable=False, server_default=''))
    op.add_column('remote_testings', sa.Column('appeal_file_path', sa.String(length=512), nullable=False, server_default=''))
    op.add_column('remote_testings', sa.Column('appeal_file_size', sa.Integer(), nullable=False, server_default='0'))
    # 申诉状态：新增列并回填存量（原申诉成功布尔 → 申诉成功）
    op.add_column('remote_testings', sa.Column('appeal_status', sa.String(length=16), nullable=False, server_default=''))
    op.execute("UPDATE remote_testings SET appeal_status = 'success' WHERE appeal_success = true")
    # 废弃列：先 drop 外键约束（appeal_report_id → reports.id）与标题索引，再 drop 列
    op.drop_constraint('remote_testings_appeal_report_id_fkey', 'remote_testings', type_='foreignkey')
    op.drop_index(op.f('ix_remote_testings_title'), table_name='remote_testings')
    op.drop_column('remote_testings', 'appeal_report_id')
    op.drop_column('remote_testings', 'test_time')
    op.drop_column('remote_testings', 'title')
    # 系统名称索引（替换原标题索引）
    op.create_index(op.f('ix_remote_testings_system_name'), 'remote_testings', ['system_name'], unique=False)

    # ---- 漏洞来源口径重构：旧值一次性重置为 0（未选择） ----
    op.execute("UPDATE vulns SET source = 0")


def downgrade() -> None:
    # ---- 远程检测：还原废弃列与申诉成功布尔 ----
    op.drop_index(op.f('ix_remote_testings_system_name'), table_name='remote_testings')
    op.add_column('remote_testings', sa.Column('title', sa.String(length=255), nullable=False, server_default=''))
    op.add_column('remote_testings', sa.Column('test_time', sa.String(length=32), nullable=False, server_default=''))
    op.add_column('remote_testings', sa.Column('appeal_report_id', sa.Integer(), nullable=True))
    op.add_column('remote_testings', sa.Column('appeal_success', sa.Boolean(), nullable=False, server_default=sa.text('false')))
    op.create_index(op.f('ix_remote_testings_title'), 'remote_testings', ['title'], unique=False)
    op.create_foreign_key('remote_testings_appeal_report_id_fkey', 'remote_testings', 'reports', ['appeal_report_id'], ['id'])
    op.execute("UPDATE remote_testings SET appeal_success = true WHERE appeal_status = 'success'")
    op.drop_column('remote_testings', 'appeal_status')
    op.drop_column('remote_testings', 'appeal_file_size')
    op.drop_column('remote_testings', 'appeal_file_path')
    op.drop_column('remote_testings', 'appeal_file_name')
    op.drop_column('remote_testings', 'appeal_method')
    op.drop_column('remote_testings', 'vuln_type')
    op.drop_column('remote_testings', 'vuln_name')
    op.drop_column('remote_testings', 'is_external')
    op.drop_column('remote_testings', 'notified_unit')
    op.drop_column('remote_testings', 'notice_time')
