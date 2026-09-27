"""P2-1：角色数据范围与用户组织查询索引。

Revision ID: a9b0c1d2e3f4
Revises: e7f8a9b0c1d2
Create Date: 2026-09-27

- P2-1：`roles.data_scope` 默认 `department`。超级管理员由 `permissions=["*"]` 始终按
  `all` 处理；存量其它角色默认按组织范围，无组织归属的用户不自动获得全量数据。
P2-4 的 trigram 索引仍按既有决策由 `scripts/enable_trgm_indexes.py` 显式运维启用，
不放进迁移，避免扩展权限不足阻断升级。

回滚：删除本迁移新增的索引与列。
"""
from alembic import op
import sqlalchemy as sa

revision = "a9b0c1d2e3f4"
down_revision = "e7f8a9b0c1d2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "roles",
        sa.Column("data_scope", sa.String(16), nullable=False, server_default="department"),
    )
    op.create_index("ix_group_users_user_id", "group_users", ["user_id"])
    op.create_index("ix_group_users_group_id", "group_users", ["group_id"])


def downgrade() -> None:
    op.drop_index("ix_group_users_group_id", table_name="group_users")
    op.drop_index("ix_group_users_user_id", table_name="group_users")
    op.drop_column("roles", "data_scope")
