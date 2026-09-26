"""P0-2 并发写入加固：工单序号计数器 / 显示编号唯一索引 / 任务幂等键 / 自动导出幂等键

Revision ID: c1d2e3f4a5b6
Revises: b9c0d1e2f3a4
Create Date: 2026-09-26

背景（ROADMAP P0-2）：
- 工单序号原先「查询当日最大序号 + 1」，并发创建会分配到同一序号（进而同一工单ID）；
  新增 `ticket_seq_counters` 单行计数器表，分配改为 `INSERT ... ON CONFLICT DO UPDATE
  SET last_seq = GREATEST(...) + 1 RETURNING`，同日编号分配原子且单调（两表共用一个序列）。
- 显示编号（手动值或 receive_time+序号派生）新增**表达式唯一索引**：请求前的查询校验
  无法覆盖并发窗口，数据库唯一索引是最终保障。
- `task_dedup_keys`：队列重试（至少一次投递）下的任务幂等键。
- `export_jobs.dedup_key`：自动导出的幂等锚点（`auto:<批次ID>`，唯一约束允许多个 NULL）。
"""
from alembic import op
import sqlalchemy as sa

revision = "c1d2e3f4a5b6"
down_revision = "b9c0d1e2f3a4"
branch_labels = None
depends_on = None

# 与 app/models/special.py::_TICKET_NO_EXPR、core/ticket_id.py::derive_ticket_id 严格同口径
_TICKET_NO_EXPR = (
    "coalesce(nullif(ticket_id_manual, ''), "
    "case when receive_time <> '' and ticket_seq <> 0 "
    "then substr(replace(receive_time, '-', ''), 1, 8) || '-' || cast(ticket_seq as varchar) end)"
)


def _assert_no_duplicate_ticket_ids(bind, table: str) -> None:
    """唯一索引前置守卫：存量重号必须人工处理，绝不静默丢弃/改写业务数据。"""
    rows = bind.execute(sa.text(
        f"SELECT ticket_no, count(*) FROM (SELECT {_TICKET_NO_EXPR} AS ticket_no FROM {table}) t "
        "WHERE ticket_no IS NOT NULL GROUP BY ticket_no HAVING count(*) > 1 LIMIT 20"
    )).all()
    if rows:
        detail = "、".join(f"{r[0]}（{r[1]} 条）" for r in rows)
        raise RuntimeError(
            f"{table} 存在重复的显示工单ID：{detail}。请先人工合并或重新编号"
            "（以 ticket_id_manual 为准）后再执行本迁移。"
        )


def upgrade() -> None:
    op.create_table(
        "ticket_seq_counters",
        sa.Column("receive_date", sa.String(length=32), primary_key=True),
        sa.Column("last_seq", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("update_time", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
    )
    op.create_table(
        "task_dedup_keys",
        sa.Column("key", sa.String(length=128), primary_key=True),
        sa.Column("create_time", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_task_dedup_keys_create_time", "task_dedup_keys", ["create_time"])

    op.add_column("export_jobs", sa.Column("dedup_key", sa.String(length=128), nullable=True))
    op.create_index("uq_export_jobs_dedup_key", "export_jobs", ["dedup_key"], unique=True)

    bind = op.get_bind()
    for table, index_name in (
        ("testing_plans", "uq_testing_plans_ticket_no"),
        ("nonpen_plans", "uq_nonpen_plans_ticket_no"),
    ):
        _assert_no_duplicate_ticket_ids(bind, table)
        op.execute(f"CREATE UNIQUE INDEX {index_name} ON {table} ({_TICKET_NO_EXPR})")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_nonpen_plans_ticket_no")
    op.execute("DROP INDEX IF EXISTS uq_testing_plans_ticket_no")
    op.drop_index("uq_export_jobs_dedup_key", table_name="export_jobs")
    op.drop_column("export_jobs", "dedup_key")
    op.drop_index("ix_task_dedup_keys_create_time", table_name="task_dedup_keys")
    op.drop_table("task_dedup_keys")
    op.drop_table("ticket_seq_counters")
