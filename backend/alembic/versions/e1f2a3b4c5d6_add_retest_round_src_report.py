"""add retest round src report id

复测轮次新增「源报告」外键（`testing_plan_retest_rounds.src_report_id`）。

背景：报告与复测轮次原先只有 `report_id`（指向本轮新生成的**复测报告**）与 `source`
自由文本（如「报告《20260730XX渗透测试报告》发起复测」），因此无法可靠回答
「某份初测报告是否已发起过复测」—— 结论输出与报告列表需要按报告维度区分
「未发起复测 / 复测中 / 复测完成」，靠标题文本匹配过于脆弱。

写入侧：`api/v1/reports.py::retest_report` 发起复测时记录源报告 ID；
手动流转与报告导入复测无源报告，保持 NULL。删除源报告时 SET NULL（不连带删除轮次）。
存量数据由 `scripts/backfill_retest_src_report.py` 按 `source` 文本回填。

幂等：仅当列不存在时新增（重复执行为空操作）；SQLite 侧由 `app/db.py` 轻量迁移兜底。

Revision ID: e1f2a3b4c5d6
Revises: d9e0f1a2b3c4
Create Date: 2026-09-19 00:00:00

"""
from alembic import op
import sqlalchemy as sa


revision = 'e1f2a3b4c5d6'
down_revision = 'd9e0f1a2b3c4'
branch_labels = None
depends_on = None

_TABLE = 'testing_plan_retest_rounds'


def _has_column(column: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return any(col["name"] == column for col in inspector.get_columns(_TABLE))


def upgrade() -> None:
    if _has_column('src_report_id'):
        return
    op.add_column(
        'testing_plan_retest_rounds',
        sa.Column('src_report_id', sa.Integer(), nullable=True),
    )
    op.create_index(
        'ix_testing_plan_retest_rounds_src_report_id',
        'testing_plan_retest_rounds', ['src_report_id'], unique=False,
    )
    op.create_foreign_key(
        'testing_plan_retest_rounds_src_report_id_fkey',
        'testing_plan_retest_rounds', 'reports', ['src_report_id'], ['id'], ondelete='SET NULL',
    )


def downgrade() -> None:
    if not _has_column('src_report_id'):
        return
    op.drop_constraint(
        'testing_plan_retest_rounds_src_report_id_fkey',
        'testing_plan_retest_rounds', type_='foreignkey',
    )
    op.drop_index(
        'ix_testing_plan_retest_rounds_src_report_id',
        table_name='testing_plan_retest_rounds',
    )
    op.drop_column('testing_plan_retest_rounds', 'src_report_id')
