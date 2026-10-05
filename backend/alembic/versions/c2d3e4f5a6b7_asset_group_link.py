"""asset group link: group member uniqueness and assets.group_id index

资产负责人自动同步要求「组织内同名成员唯一」；同时为资产按组织过滤补充索引。
历史数据若存在同组织同名成员，迁移前保留 id 最小的一条。

Revision ID: c2d3e4f5a6b7
Revises: b1c2d3e4f5a6
Create Date: 2026-10-05
"""
from alembic import op


revision = "c2d3e4f5a6b7"
down_revision = "b1c2d3e4f5a6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DELETE FROM group_members gm
        USING group_members keep
        WHERE gm.group_id = keep.group_id
          AND gm.name = keep.name
          AND gm.id > keep.id
        """
    )
    op.create_unique_constraint(
        "uq_group_member_group_name", "group_members", ["group_id", "name"]
    )
    op.create_index("ix_assets_group_id", "assets", ["group_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_assets_group_id", table_name="assets")
    op.drop_constraint("uq_group_member_group_name", "group_members", type_="unique")
