"""P1 业务闭环批次：SLA / 站内消息 / 通知投递 / 报告模板 / 导入治理 / 开放 API / 看板视图

Revision ID: e7f8a9b0c1d2
Revises: d3e4f5a6b7c8
Create Date: 2026-09-26

本迁移一次性建立 P1-1 ~ P1-7 所需的表与列（同批次发布，一条迁移便于统一回滚）：

- P1-1 SLA：`sla_config` / `sla_policies` / `sla_extensions` 三表 + `vulns.due_at`
  （存量漏洞留 NULL＝未参与 SLA，由 `POST /sla/recalculate` 显式重算，符合
   「策略变更默认只影响未来新漏洞；历史批量重算必须显式执行」的验收口径）；
- P1-2 站内消息：`messages.link`（深链）+ `create_time` 索引；
- P1-3 通知投递：`notify_deliveries` 表（状态 / 尝试次数 / 下次重试 / 死信原因）；
- P1-4 报告模板：`report_templates` 表 + `export_jobs.template_id/template_version/template_name`
  （历史导出记录的 template_name 为空＝当时使用包内默认模板）；
- P1-5 导入治理：`import_record_changes` 表 + `import_records.merge_vul_id/outcome/outcome_reason`；
- P1-6 开放 API：`api_idempotency_keys` 表 + `personal_access_tokens.scope`（存量令牌默认 `full`，
  = 迁移前能力，避免兼容性回归）+ `operation_logs.request_id`（审计与请求追踪打通）；
- P1-7 看板视图：`dashboard_views` 表。

回退：`downgrade` 逐项删除本迁移创建的表/列/索引，不触碰任何存量数据。
"""
from alembic import op
import sqlalchemy as sa

revision = "e7f8a9b0c1d2"
down_revision = "d3e4f5a6b7c8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ---------- P1-1 SLA ----------
    op.create_table(
        "sla_config",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("day_basis", sa.String(16), nullable=False, server_default="natural"),
        sa.Column("default_days", sa.Integer(), nullable=False, server_default="7"),
        sa.Column("warn_hours", sa.Integer(), nullable=False, server_default="24"),
        sa.Column("allow_extend", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("workdays", sa.JSON(), nullable=False),
        sa.Column("holidays", sa.JSON(), nullable=False),
        sa.Column("stop_statuses", sa.JSON(), nullable=False),
        sa.Column("remark", sa.Text(), nullable=False, server_default=""),
        sa.Column("updated_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("update_time", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
    )
    op.create_table(
        "sla_policies",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("level", sa.Integer(), nullable=False, unique=True),
        sa.Column("days", sa.Integer(), nullable=False, server_default="7"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("remark", sa.String(255), nullable=False, server_default=""),
        sa.Column("create_time", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("update_time", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
    )
    op.create_table(
        "sla_extensions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "vul_id", sa.Integer(), sa.ForeignKey("vulns.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("old_due_at", sa.DateTime(), nullable=True),
        sa.Column("new_due_at", sa.DateTime(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False, server_default=""),
        sa.Column("operator_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("username", sa.String(64), nullable=False, server_default=""),
        sa.Column("create_time", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_sla_extensions_vul_id", "sla_extensions", ["vul_id"])
    op.add_column("vulns", sa.Column("due_at", sa.DateTime(), nullable=True))
    op.create_index("ix_vulns_due_at", "vulns", ["due_at"])

    # ---------- P1-2 站内消息 ----------
    op.add_column(
        "messages", sa.Column("link", sa.String(255), nullable=False, server_default=""),
    )
    op.create_index("ix_messages_create_time", "messages", ["create_time"])

    # ---------- P1-4 报告模板中心（先建表，export_jobs 外键依赖它） ----------
    op.create_table(
        "report_templates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("report_type", sa.String(16), nullable=False, server_default="all"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("file_path", sa.String(512), nullable=False, server_default=""),
        sa.Column("original_filename", sa.String(255), nullable=False, server_default=""),
        sa.Column("size_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("anchors", sa.JSON(), nullable=False),
        sa.Column("remark", sa.Text(), nullable=False, server_default=""),
        sa.Column("creator_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("create_time", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("update_time", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("name", "version", name="uq_report_template_name_version"),
    )
    op.create_index("ix_report_templates_name", "report_templates", ["name"])
    op.add_column(
        "export_jobs",
        sa.Column("template_id", sa.Integer(), sa.ForeignKey("report_templates.id", ondelete="SET NULL"),
                  nullable=True),
    )
    op.add_column(
        "export_jobs",
        sa.Column("template_version", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "export_jobs",
        sa.Column("template_name", sa.String(128), nullable=False, server_default=""),
    )

    # ---------- P1-3 通知投递记录 ----------
    op.create_table(
        "notify_deliveries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "channel_id", sa.Integer(),
            sa.ForeignKey("notification_channels.id", ondelete="SET NULL"), nullable=True,
        ),
        sa.Column("channel_name", sa.String(64), nullable=False, server_default=""),
        sa.Column("channel_type", sa.String(16), nullable=False, server_default=""),
        sa.Column("event", sa.String(32), nullable=False, server_default=""),
        sa.Column("title", sa.String(255), nullable=False, server_default=""),
        sa.Column("content", sa.Text(), nullable=False, server_default=""),
        sa.Column("target", sa.String(255), nullable=False, server_default=""),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("http_status", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text(), nullable=False, server_default=""),
        sa.Column("next_retry_at", sa.DateTime(), nullable=True),
        sa.Column("dead_letter_reason", sa.Text(), nullable=False, server_default=""),
        sa.Column("request_time", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("last_attempt_at", sa.DateTime(), nullable=True),
        sa.Column("finish_time", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_notify_deliveries_channel_id", "notify_deliveries", ["channel_id"])
    op.create_index("ix_notify_deliveries_event", "notify_deliveries", ["event"])
    op.create_index("ix_notify_deliveries_status", "notify_deliveries", ["status"])
    op.create_index("ix_notify_deliveries_next_retry_at", "notify_deliveries", ["next_retry_at"])
    op.create_index("ix_notify_deliveries_request_time", "notify_deliveries", ["request_time"])

    # ---------- P1-5 导入数据治理 ----------
    op.add_column(
        "import_records",
        sa.Column("merge_vul_id", sa.Integer(), sa.ForeignKey("vulns.id"), nullable=True),
    )
    op.add_column(
        "import_records", sa.Column("outcome", sa.String(16), nullable=False, server_default=""),
    )
    op.add_column(
        "import_records", sa.Column("outcome_reason", sa.Text(), nullable=False, server_default=""),
    )
    op.create_table(
        "import_record_changes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "record_id", sa.Integer(),
            sa.ForeignKey("import_records.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("field", sa.String(32), nullable=False, server_default=""),
        sa.Column("old_value", sa.Text(), nullable=False, server_default=""),
        sa.Column("new_value", sa.Text(), nullable=False, server_default=""),
        sa.Column("source", sa.String(16), nullable=False, server_default="manual"),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("username", sa.String(64), nullable=False, server_default=""),
        sa.Column("create_time", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_import_record_changes_record_id", "import_record_changes", ["record_id"])

    # ---------- P1-6 开放 API ----------
    op.add_column(
        "personal_access_tokens",
        sa.Column("scope", sa.String(16), nullable=False, server_default="full"),
    )
    op.create_table(
        "api_idempotency_keys",
        sa.Column("key", sa.String(191), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("endpoint", sa.String(128), nullable=False, server_default=""),
        sa.Column("payload_hash", sa.String(64), nullable=False, server_default=""),
        sa.Column("status_code", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("response", sa.Text(), nullable=False, server_default=""),
        sa.Column("create_time", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_api_idempotency_keys_user_id", "api_idempotency_keys", ["user_id"])
    op.create_index("ix_api_idempotency_keys_create_time", "api_idempotency_keys", ["create_time"])
    op.add_column(
        "operation_logs",
        sa.Column("request_id", sa.String(64), nullable=False, server_default=""),
    )
    op.create_index("ix_operation_logs_request_id", "operation_logs", ["request_id"])

    # ---------- P1-7 看板视图 ----------
    op.create_table(
        "dashboard_views",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("scope", sa.String(16), nullable=False, server_default="personal"),
        sa.Column("department", sa.String(128), nullable=False, server_default=""),
        sa.Column("query", sa.JSON(), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("create_time", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("update_time", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_dashboard_views_user_id", "dashboard_views", ["user_id"])


def downgrade() -> None:
    # P1-7
    op.drop_index("ix_dashboard_views_user_id", table_name="dashboard_views")
    op.drop_table("dashboard_views")

    # P1-6
    op.drop_index("ix_operation_logs_request_id", table_name="operation_logs")
    op.drop_column("operation_logs", "request_id")
    op.drop_index("ix_api_idempotency_keys_create_time", table_name="api_idempotency_keys")
    op.drop_index("ix_api_idempotency_keys_user_id", table_name="api_idempotency_keys")
    op.drop_table("api_idempotency_keys")
    op.drop_column("personal_access_tokens", "scope")

    # P1-5
    op.drop_index("ix_import_record_changes_record_id", table_name="import_record_changes")
    op.drop_table("import_record_changes")
    op.drop_column("import_records", "outcome_reason")
    op.drop_column("import_records", "outcome")
    op.drop_column("import_records", "merge_vul_id")

    # P1-3
    for name in (
        "ix_notify_deliveries_request_time", "ix_notify_deliveries_next_retry_at",
        "ix_notify_deliveries_status", "ix_notify_deliveries_event",
        "ix_notify_deliveries_channel_id",
    ):
        op.drop_index(name, table_name="notify_deliveries")
    op.drop_table("notify_deliveries")

    # P1-4
    op.drop_column("export_jobs", "template_name")
    op.drop_column("export_jobs", "template_version")
    op.drop_column("export_jobs", "template_id")
    op.drop_index("ix_report_templates_name", table_name="report_templates")
    op.drop_table("report_templates")

    # P1-2
    op.drop_index("ix_messages_create_time", table_name="messages")
    op.drop_column("messages", "link")

    # P1-1
    op.drop_index("ix_vulns_due_at", table_name="vulns")
    op.drop_column("vulns", "due_at")
    op.drop_index("ix_sla_extensions_vul_id", table_name="sla_extensions")
    op.drop_table("sla_extensions")
    op.drop_table("sla_policies")
    op.drop_table("sla_config")
