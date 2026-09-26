"""P0-4 热点查询索引：漏扫 items 表达式索引 + 列表高频筛选字段索引

Revision ID: f3a4b5c6d7e8
Revises: d2e3f4a5b6c7
Create Date: 2026-09-26

背景（ROADMAP P0-4）：
- 「仅可进行」原先取回最多 10000 条后在应用层过滤，数据增长后读取与内存线性放大；
  已改为 SQL 侧 `items ->> '<key>'` 判定（`plan_query.nonpen_actionable_condition`），
  本迁移为三个固定键建**表达式索引**，使 `(a) OR (b) OR (c)` 可由 BitmapOr 组合索引扫描。
  注意：表达式必须与查询中**逐字一致**（键名内联为字面量，不能用绑定参数），否则规划器不采信。
- 补齐列表高频筛选字段索引：漏洞提交时间、工单接收时间 / 状态 / 部门、报告更新时间与工单归属。
  （漏洞标题 / 状态、审计时间原本已有索引，不重复创建。）

回退：`downgrade` 逐个删除本迁移创建的索引，不触碰任何数据。
"""
from alembic import op
import sqlalchemy as sa

revision = "f3a4b5c6d7e8"
down_revision = "d2e3f4a5b6c7"
branch_labels = None
depends_on = None

# 「仅可进行」表达式索引：键名与 plan_query.nonpen_actionable_condition 中的字面量一致
_NONPEN_ITEM_KEYS = ("baseline", "host", "web")

# 普通列索引：(索引名, 表名, 列名)
_PLAIN_INDEXES = (
    ("ix_vulns_submit_time", "vulns", "submit_time"),
    ("ix_testing_plans_department", "testing_plans", "department"),
    ("ix_testing_plans_receive_time", "testing_plans", "receive_time"),
    ("ix_testing_plans_status", "testing_plans", "status"),
    ("ix_reports_update_time", "reports", "update_time"),
    ("ix_reports_testing_plan_id", "reports", "testing_plan_id"),
)


def upgrade() -> None:
    for name, table, column in _PLAIN_INDEXES:
        op.create_index(name, table, [column])
    for key in _NONPEN_ITEM_KEYS:
        op.create_index(
            f"ix_nonpen_plans_item_{key}", "nonpen_plans",
            [sa.text(f"(items -> '{key}' ->> 'status')")],
        )


def downgrade() -> None:
    for key in _NONPEN_ITEM_KEYS:
        op.drop_index(f"ix_nonpen_plans_item_{key}", table_name="nonpen_plans")
    for name, table, _column in reversed(_PLAIN_INDEXES):
        op.drop_index(name, table_name=table)
