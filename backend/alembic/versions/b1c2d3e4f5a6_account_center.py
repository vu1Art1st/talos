"""account center: sessions, action tokens, unique email and message prefs

Revision ID: b1c2d3e4f5a6
Revises: a9b0c1d2e3f4
Create Date: 2026-10-04
"""
from alembic import op
import sqlalchemy as sa


revision = "b1c2d3e4f5a6"
down_revision = "a9b0c1d2e3f4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        DECLARE duplicate_email text;
        BEGIN
            SELECT lower(email)
            INTO duplicate_email
            FROM users
            WHERE email <> ''
            GROUP BY lower(email)
            HAVING count(*) > 1
            LIMIT 1;
            IF duplicate_email IS NOT NULL THEN
                RAISE EXCEPTION '检测到重复用户邮箱，请先处理: %', duplicate_email;
            END IF;
        END $$;
        """
    )
    op.execute("UPDATE users SET email = lower(btrim(email)) WHERE email <> ''")
    op.add_column(
        "users",
        sa.Column(
            "message_prefs",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'::json"),
        ),
    )
    op.create_index(
        "uq_users_email_lower",
        "users",
        [sa.text("lower(email)")],
        unique=True,
        postgresql_where=sa.text("email <> ''"),
    )

    op.create_table(
        "user_sessions",
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("create_time", sa.DateTime(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("ip", sa.String(length=64), nullable=False),
        sa.Column("user_agent", sa.String(length=256), nullable=False),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("session_id"),
    )
    op.create_index("ix_user_sessions_user_id", "user_sessions", ["user_id"])
    op.create_index("ix_user_sessions_create_time", "user_sessions", ["create_time"])
    op.create_index("ix_user_sessions_expires_at", "user_sessions", ["expires_at"])
    op.create_index("ix_user_sessions_revoked_at", "user_sessions", ["revoked_at"])

    op.create_table(
        "account_action_tokens",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("purpose", sa.String(length=32), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("new_email", sa.String(length=128), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("used_at", sa.DateTime(), nullable=True),
        sa.Column("create_time", sa.DateTime(), nullable=False),
        sa.Column("request_ip", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_account_action_tokens_user_id", "account_action_tokens", ["user_id"])
    op.create_index("ix_account_action_tokens_purpose", "account_action_tokens", ["purpose"])
    op.create_index(
        "ix_account_action_tokens_token_hash",
        "account_action_tokens",
        ["token_hash"],
        unique=True,
    )
    op.create_index("ix_account_action_tokens_expires_at", "account_action_tokens", ["expires_at"])
    op.create_index("ix_account_action_tokens_create_time", "account_action_tokens", ["create_time"])


def downgrade() -> None:
    op.drop_index("ix_account_action_tokens_create_time", table_name="account_action_tokens")
    op.drop_index("ix_account_action_tokens_expires_at", table_name="account_action_tokens")
    op.drop_index("ix_account_action_tokens_token_hash", table_name="account_action_tokens")
    op.drop_index("ix_account_action_tokens_purpose", table_name="account_action_tokens")
    op.drop_index("ix_account_action_tokens_user_id", table_name="account_action_tokens")
    op.drop_table("account_action_tokens")

    op.drop_index("ix_user_sessions_revoked_at", table_name="user_sessions")
    op.drop_index("ix_user_sessions_expires_at", table_name="user_sessions")
    op.drop_index("ix_user_sessions_create_time", table_name="user_sessions")
    op.drop_index("ix_user_sessions_user_id", table_name="user_sessions")
    op.drop_table("user_sessions")

    op.drop_index("uq_users_email_lower", table_name="users")
    op.drop_column("users", "message_prefs")
