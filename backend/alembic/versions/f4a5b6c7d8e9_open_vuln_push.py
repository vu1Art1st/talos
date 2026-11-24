"""open vuln push: external refs and agent images

Revision ID: f4a5b6c7d8e9
Revises: c2d3e4f5a6b7
Create Date: 2026-11-19
"""
from alembic import op
import sqlalchemy as sa


revision = "f4a5b6c7d8e9"
down_revision = "c2d3e4f5a6b7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "vul_external_refs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("vul_id", sa.Integer(), nullable=False),
        sa.Column("testing_plan_id", sa.Integer(), nullable=False),
        sa.Column("source_system", sa.String(length=64), nullable=False),
        sa.Column("external_id", sa.String(length=191), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("source_payload_json", sa.JSON(), nullable=True),
        sa.Column("converter_version", sa.String(length=32), nullable=False),
        sa.Column("first_push_time", sa.DateTime(), nullable=False),
        sa.Column("last_push_time", sa.DateTime(), nullable=False),
        sa.Column("last_operator_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["last_operator_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["testing_plan_id"], ["testing_plans.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["vul_id"], ["vulns.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_system", "external_id", name="uq_vul_external_ref_source_id",
        ),
    )
    op.create_index(
        "ix_vul_external_refs_vul_id", "vul_external_refs", ["vul_id"], unique=False,
    )
    op.create_index(
        "ix_vul_external_refs_testing_plan_id", "vul_external_refs",
        ["testing_plan_id"], unique=False,
    )
    op.create_index(
        "ix_vul_external_refs_source_system", "vul_external_refs",
        ["source_system"], unique=False,
    )

    op.create_table(
        "vul_external_images",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("plan_id", sa.Integer(), nullable=False),
        sa.Column("source_system", sa.String(length=64), nullable=False),
        sa.Column("external_image_id", sa.String(length=191), nullable=True),
        sa.Column("file_name", sa.String(length=64), nullable=False),
        sa.Column("mime_type", sa.String(length=64), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("uploader_id", sa.Integer(), nullable=True),
        sa.Column("create_time", sa.DateTime(), nullable=False),
        sa.Column("last_used_time", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["plan_id"], ["testing_plans.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["uploader_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "plan_id", "source_system", "sha256", name="uq_vul_external_image_plan_sha",
        ),
        sa.UniqueConstraint(
            "plan_id", "source_system", "external_image_id",
            name="uq_vul_external_image_plan_external",
        ),
        sa.UniqueConstraint("file_name", name="uq_vul_external_image_file_name"),
    )
    op.create_index(
        "ix_vul_external_images_plan_id", "vul_external_images",
        ["plan_id"], unique=False,
    )
    op.create_index(
        "ix_vul_external_images_source_system", "vul_external_images",
        ["source_system"], unique=False,
    )
    op.create_index(
        "ix_vul_external_images_sha256", "vul_external_images",
        ["sha256"], unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_vul_external_images_sha256", table_name="vul_external_images")
    op.drop_index("ix_vul_external_images_source_system", table_name="vul_external_images")
    op.drop_index("ix_vul_external_images_plan_id", table_name="vul_external_images")
    op.drop_table("vul_external_images")

    op.drop_index("ix_vul_external_refs_source_system", table_name="vul_external_refs")
    op.drop_index("ix_vul_external_refs_testing_plan_id", table_name="vul_external_refs")
    op.drop_index("ix_vul_external_refs_vul_id", table_name="vul_external_refs")
    op.drop_table("vul_external_refs")
