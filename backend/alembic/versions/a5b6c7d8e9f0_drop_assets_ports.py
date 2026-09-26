"""P0-6 遗留惰性列清理（1/5）：删除 assets.ports

Revision ID: a5b6c7d8e9f0
Revises: f3a4b5c6d7e8
Create Date: 2026-09-26

删除前核查（2026-09-26，逐项留痕）：
- **生产无读写**：`app/`、`scripts/`、`frontend/` 全仓检索无 `ports` 列引用，值早在历史版本
  迁入 `port_services`（JSON），本列只剩旧数据；删列不影响任何读写路径。
- **备份可用**：升级前按 `docs/DEPLOY.md` 完成一次备份；本迁移不改写数据，回滚由下方
  `downgrade` 提供（重建同名列，类型与原定义一致）。
- **降级路径完整**：`upgrade` 只删这一列，`downgrade` 精确恢复；独立专项，不夹带其它重构。
- **登记守卫**：`tests/test_schema_consistency.DEPRECATED_COLUMNS` 同时锁定「模型不得再映射」
  与「迁移必须显式删除」两个方向，避免 PostgreSQL 残留 NOT NULL 僵尸列（历史事故：
  `remote_testings.appeal_success`）。
"""
from alembic import op
import sqlalchemy as sa

revision = "a5b6c7d8e9f0"
down_revision = "f3a4b5c6d7e8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("assets", "ports")


def downgrade() -> None:
    op.add_column("assets", sa.Column("ports", sa.JSON(), nullable=True))
