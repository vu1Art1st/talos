"""remote testing link asset and vuln

远程检测（2026-09-11 需求）：系统名称支持关联资产台账、漏洞名称支持关联漏洞库。
- 新增 asset_id（FK assets.id）、vuln_id（FK vulns.id，均带索引）与 asset_belong（资产归属文本）；
- department 语义调整为「部门」（选资产自动带出）。

幂等：模型已不再映射的库（create_all 新库）或列已存在的库直接跳过；与
app/db.py `_migrate_lightweight` 的 SQLite 加列保持同轨（双轨同步铁律）。

Revision ID: c7d8e9f0a1b2
Revises: b4c5d6e7f8a9
Create Date: 2026-09-11 00:00:00

"""
from alembic import op
import sqlalchemy as sa


revision = 'c7d8e9f0a1b2'
down_revision = 'b4c5d6e7f8a9'
branch_labels = None
depends_on = None

_COLUMNS = (
    ("asset_id", sa.Column("asset_id", sa.Integer(), nullable=True)),
    ("asset_belong", sa.Column("asset_belong", sa.String(length=128), nullable=False, server_default="")),
    ("vuln_id", sa.Column("vuln_id", sa.Integer(), nullable=True)),
)


def _existing_columns() -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {c["name"] for c in inspector.get_columns("remote_testings")}


def _existing_indexes() -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {i["name"] for i in inspector.get_indexes("remote_testings")}


def _existing_fkeys() -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {fk["name"] for fk in inspector.get_foreign_keys("remote_testings")}


def upgrade() -> None:
    existing = _existing_columns()
    for name, column in _COLUMNS:
        if name not in existing:
            op.add_column("remote_testings", column)
    indexes = _existing_indexes()
    if "ix_remote_testings_asset_id" not in indexes:
        op.create_index("ix_remote_testings_asset_id", "remote_testings", ["asset_id"])
    if "ix_remote_testings_vuln_id" not in indexes:
        op.create_index("ix_remote_testings_vuln_id", "remote_testings", ["vuln_id"])
    # 外键约束无法在 add_column 增量场景下可靠探测，按列新建时一并创建
    if "asset_id" not in existing:
        op.create_foreign_key(
            "remote_testings_asset_id_fkey", "remote_testings", "assets", ["asset_id"], ["id"],
        )
    if "vuln_id" not in existing:
        op.create_foreign_key(
            "remote_testings_vuln_id_fkey", "remote_testings", "vulns", ["vuln_id"], ["id"],
        )


def downgrade() -> None:
    existing = _existing_columns()
    indexes = _existing_indexes()
    fkeys = _existing_fkeys()
    if "vuln_id" in existing:
        if "ix_remote_testings_vuln_id" in indexes:
            op.drop_index("ix_remote_testings_vuln_id", table_name="remote_testings")
        if "remote_testings_vuln_id_fkey" in fkeys:
            op.drop_constraint("remote_testings_vuln_id_fkey", "remote_testings", type_="foreignkey")
        op.drop_column("remote_testings", "vuln_id")
    if "asset_id" in existing:
        if "ix_remote_testings_asset_id" in indexes:
            op.drop_index("ix_remote_testings_asset_id", table_name="remote_testings")
        if "remote_testings_asset_id_fkey" in fkeys:
            op.drop_constraint("remote_testings_asset_id_fkey", "remote_testings", type_="foreignkey")
        op.drop_column("remote_testings", "asset_id")
    if "asset_belong" in existing:
        op.drop_column("remote_testings", "asset_belong")
