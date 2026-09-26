"""P0-3 后台任务生命周期：导出与导入批次补租约 / 心跳 / 重试 / 死信列

Revision ID: d2e3f4a5b6c7
Revises: c1d2e3f4a5b6
Create Date: 2026-09-26

方案说明（ROADMAP P0-3 的「是否合并为统一任务表」评估结论）：**不合并**。导入与导出的
业务列、状态取值、消费方都不同，合并表会牵动报告与导入两条主链路的全部读写点；
改为两表补齐同一组生命周期列，状态机实现统一收敛在 `services/task_lifecycle.py`。

存量行处理：`attempts` / `dead_letter_reason` 带 server_default，历史行直接取默认值；
租约列留 NULL（表示「迁移前写入」），启动回收扫描按 create_time 保守判定为孤儿任务。
"""
from alembic import op
import sqlalchemy as sa

revision = "d2e3f4a5b6c7"
down_revision = "c1d2e3f4a5b6"
branch_labels = None
depends_on = None

# 两张任务表共用同一组生命周期列（与 models/report.py、models/imports.py 一一对应）
_LIFECYCLE_COLUMNS = (
    sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
    sa.Column("last_heartbeat", sa.DateTime(), nullable=True),
    sa.Column("lease_until", sa.DateTime(), nullable=True),
    sa.Column("next_retry_at", sa.DateTime(), nullable=True),
    sa.Column("dead_letter_reason", sa.Text(), nullable=False, server_default=""),
)

_TABLES = ("export_jobs", "import_batches")


def upgrade() -> None:
    for table in _TABLES:
        for column in _LIFECYCLE_COLUMNS:
            op.add_column(table, column.copy())
        op.create_index(f"ix_{table}_lease_until", table, ["lease_until"])
        op.create_index(f"ix_{table}_next_retry_at", table, ["next_retry_at"])


def downgrade() -> None:
    for table in _TABLES:
        op.drop_index(f"ix_{table}_next_retry_at", table_name=table)
        op.drop_index(f"ix_{table}_lease_until", table_name=table)
        for column in reversed(_LIFECYCLE_COLUMNS):
            op.drop_column(table, column.name)
