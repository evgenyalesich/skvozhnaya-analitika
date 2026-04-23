"""add telegram chat memberships

Revision ID: 0022_add_telegram_chat_memberships
Revises: 0021_add_platform_utm_columns
Create Date: 2026-03-26
"""

from alembic import op
import sqlalchemy as sa


revision = "0022_add_telegram_chat_memberships"
down_revision = "0021_add_platform_utm_columns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "telegram_chat_memberships",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("chat_id", sa.String(length=64), nullable=False),
        sa.Column("tg_user_id", sa.BIGINT(), nullable=False),
        sa.Column("username", sa.String(length=128), nullable=True),
        sa.Column("is_member", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("first_seen_member_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("last_seen_member_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("last_status_change_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("source", sa.String(length=32), nullable=False, server_default=sa.text("'full_sync'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("chat_id", "tg_user_id", name="uq_telegram_chat_membership"),
    )
    op.create_index("ix_telegram_chat_memberships_chat_id", "telegram_chat_memberships", ["chat_id"], unique=False)
    op.create_index("ix_telegram_chat_memberships_tg_user_id", "telegram_chat_memberships", ["tg_user_id"], unique=False)
    op.create_index("ix_telegram_chat_memberships_username", "telegram_chat_memberships", ["username"], unique=False)
    op.create_index(
        "idx_telegram_chat_membership_chat_member",
        "telegram_chat_memberships",
        ["chat_id", "is_member"],
        unique=False,
    )
    op.create_index(
        "idx_telegram_chat_membership_last_seen",
        "telegram_chat_memberships",
        ["chat_id", "last_seen_member_at"],
        unique=False,
    )

    op.add_column("telegram_subscription_events", sa.Column("source", sa.String(length=32), nullable=True))
    op.add_column("telegram_subscription_events", sa.Column("event_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("telegram_subscription_events", sa.Column("observed_at", sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE telegram_subscription_events SET source = 'bot_poll' WHERE source IS NULL")
    op.alter_column("telegram_subscription_events", "source", nullable=False)
    op.alter_column("telegram_subscription_events", "source", server_default=sa.text("'bot_poll'"))


def downgrade() -> None:
    op.drop_column("telegram_subscription_events", "observed_at")
    op.drop_column("telegram_subscription_events", "event_at")
    op.drop_column("telegram_subscription_events", "source")

    op.drop_index("idx_telegram_chat_membership_last_seen", table_name="telegram_chat_memberships")
    op.drop_index("idx_telegram_chat_membership_chat_member", table_name="telegram_chat_memberships")
    op.drop_index("ix_telegram_chat_memberships_username", table_name="telegram_chat_memberships")
    op.drop_index("ix_telegram_chat_memberships_tg_user_id", table_name="telegram_chat_memberships")
    op.drop_index("ix_telegram_chat_memberships_chat_id", table_name="telegram_chat_memberships")
    op.drop_table("telegram_chat_memberships")
