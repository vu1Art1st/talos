"""drop reports.status

报告「草稿(draft) / 已定稿(final)」状态功能取消：报告实体不再持有状态，
两态原先只由「导出 Word 成功后定稿」与「已定稿报告内容变更回退草稿」驱动，
无权限 / 筛选 / 统计依赖，故连同列一并移除。

本迁移幂等删除该列：列已不存在（新库由 create_all 建表、或本迁移已执行）时直接跳过。

Revision ID: b9c0d1e2f3a4
Revises: e1f2a3b4c5d6
Create Date: 2026-09-23 00:00:00

"""
from alembic import op
import sqlalchemy as sa


revision = 'b9c0d1e2f3a4'
down_revision = 'e1f2a3b4c5d6'
branch_labels = None
depends_on = None


def _has_report_status() -> bool:
    """探测报告状态列是否还在：删除前先判断，保证迁移可重复执行。"""
    inspector = sa.inspect(op.get_bind())
    return "status" in {c["name"] for c in inspector.get_columns("reports")}


def upgrade() -> None:
    if not _has_report_status():
        return
    op.drop_column("reports", "status")


def downgrade() -> None:
    # 仅恢复列结构（默认 draft）；原状态取值不可还原
    if _has_report_status():
        return
    op.add_column(
        "reports",
        sa.Column("status", sa.String(length=16), nullable=False, server_default="draft"),
    )
