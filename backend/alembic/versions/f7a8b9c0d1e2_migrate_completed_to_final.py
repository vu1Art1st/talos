"""migrate report status completed to final

需求6：报告状态机简化为「草稿/已定稿」两态，移除漏洞全闭环→completed 的自动联动。
存量「已闭环 completed」报告迁移为已定稿 final（已完成视为已定稿）。

Revision ID: f7a8b9c0d1e2
Revises: e6f7a8b9c0d1
Create Date: 2026-08-07 00:00:00

"""
from alembic import op
import sqlalchemy as sa


revision = 'f7a8b9c0d1e2'
down_revision = 'e6f7a8b9c0d1'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("UPDATE reports SET status = 'final' WHERE status = 'completed'")


def downgrade() -> None:
    # 仅迁移存量状态，不反向恢复（新状态机不再产生 completed，无法还原原语义）
    pass
