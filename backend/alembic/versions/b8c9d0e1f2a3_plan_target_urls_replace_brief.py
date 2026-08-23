"""replace testing_plans.brief with target_urls

工单「漏洞简述」(brief) 全仓无展示/导出消费，由「被测系统URL」(target_urls) 取代：
- brief 列删除（已有简述文本随迁移丢弃）；
- target_urls 为 JSON 字符串数组，选择关联资产后自动带出、可手动增删，
  作为报告导出「测试目标」表被测系统URL/域名的优先数据源（为空回退资产聚合）。

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-08-23 00:00:00

"""
from alembic import op
import sqlalchemy as sa


revision = 'b8c9d0e1f2a3'
down_revision = 'a7b8c9d0e1f2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('testing_plans', sa.Column('target_urls', sa.JSON(), nullable=True))
    op.drop_column('testing_plans', 'brief')


def downgrade() -> None:
    op.add_column('testing_plans', sa.Column('brief', sa.Text(), nullable=True))
    op.drop_column('testing_plans', 'target_urls')
