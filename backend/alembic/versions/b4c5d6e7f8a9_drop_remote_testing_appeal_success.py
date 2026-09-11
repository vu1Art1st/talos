"""drop legacy remote_testings.appeal_success

远程检测口径重构（2.12）时，模型用 appeal_status 取代了 appeal_success；迁移
e5f6a7b8c9d0 新增并回填了 appeal_status、也删除了 title / test_time / appeal_report_id，
但漏删了 appeal_success。该列在基线中为 NOT NULL 且无 server_default，模型又不再映射它，
于是 PostgreSQL 下任何 INSERT 都会报 NotNullViolationError（新建/编辑远程检测 500）。

本迁移幂等删除该遗留列：列已不存在（重建表清理过、或 create_all 建的新库）时直接跳过，
因此对「被 scripts/migrate.py 的 stamp head 跳过中间迁移」的旧库同样能安全补刀。

Revision ID: b4c5d6e7f8a9
Revises: a4b5c6d7e8f9
Create Date: 2026-09-11 00:00:00

"""
from alembic import op
import sqlalchemy as sa


revision = 'b4c5d6e7f8a9'
down_revision = 'a4b5c6d7e8f9'
branch_labels = None
depends_on = None


def _has_appeal_success() -> bool:
    """探测遗留列是否还在：删除前先判断，保证迁移可重复执行。"""
    inspector = sa.inspect(op.get_bind())
    return "appeal_success" in {c["name"] for c in inspector.get_columns("remote_testings")}


def upgrade() -> None:
    if not _has_appeal_success():
        return
    # 兜底回填：极旧库若尚未把布尔口径迁到新的申诉状态，先补数据再删列，避免信息丢失
    op.execute(
        "UPDATE remote_testings SET appeal_status = 'success' "
        "WHERE appeal_success IS TRUE AND appeal_status = ''"
    )
    op.drop_column("remote_testings", "appeal_success")


def downgrade() -> None:
    if _has_appeal_success():
        return
    op.add_column(
        "remote_testings",
        sa.Column("appeal_success", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.execute("UPDATE remote_testings SET appeal_success = TRUE WHERE appeal_status = 'success'")
