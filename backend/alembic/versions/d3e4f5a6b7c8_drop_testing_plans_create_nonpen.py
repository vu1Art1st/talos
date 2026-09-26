"""P0-6 遗留惰性列清理（5/5）：删除 testing_plans.create_nonpen

Revision ID: d3e4f5a6b7c8
Revises: c8d9e0f1a2b3
Create Date: 2026-09-26

删除前核查（2026-09-26）：
- **生产无读写**：该列由 c9d0e1f2a3b4 建出，用于「创建非渗透测试项」勾选；该标志后来改成
  **仅入参不落库**（`plan_crud.create_plan` 里 `payload.pop("create_nonpen", False)` 后即弃），
  模型早已不映射，全仓无任何列读写。
- **备份可用 / 降级完整**：升级前按 `docs/DEPLOY.md` 备份；`downgrade` 按原定义重建
  （NOT NULL + server_default=false），不影响既有行。
- **登记守卫**：`DEPRECATED_COLUMNS` 双向锁定；`tests/test_migrations.py` 的已知惰性列白名单
  随之清空（本列是最后一项）。
"""
from alembic import op
import sqlalchemy as sa

revision = "d3e4f5a6b7c8"
down_revision = "c8d9e0f1a2b3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("testing_plans", "create_nonpen")


def downgrade() -> None:
    op.add_column(
        "testing_plans",
        sa.Column("create_nonpen", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
