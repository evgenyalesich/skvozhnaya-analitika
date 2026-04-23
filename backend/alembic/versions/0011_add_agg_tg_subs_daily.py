"""Add agg_tg_subs_daily table.

Revision ID: 0011_add_agg_tg_subs_daily
Revises: 0010_add_user_block_to_raw_bot_users
Create Date: 2026-02-04
"""

from alembic import op
import sqlalchemy as sa


revision = "0011_add_agg_tg_subs_daily"
down_revision = "0010_add_user_block_to_raw_bot_users"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agg_tg_subs_daily",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("campaign", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("bot_key", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("advertising_company", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("utm_source", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("utm_campaign", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("utm_medium", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("utm_content", sa.String(length=256), nullable=False, server_default=""),
        sa.Column("utm_term", sa.String(length=256), nullable=False, server_default=""),
        sa.Column("bot_starts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("almanah_starts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("channel_subscribed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("channel_unsubscribed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("saloon_subscribed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("saloon_unsubscribed", sa.Integer(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "day",
            "campaign",
            "bot_key",
            "advertising_company",
            "utm_source",
            "utm_campaign",
            "utm_medium",
            "utm_content",
            "utm_term",
            name="uq_tg_subs_daily_dimensions",
        ),
    )
    op.create_index("idx_tg_subs_daily_group", "agg_tg_subs_daily", ["day", "campaign"], unique=False)
    op.create_index(
        "idx_tg_subs_daily_filters",
        "agg_tg_subs_daily",
        ["day", "bot_key", "advertising_company", "utm_source", "utm_campaign", "utm_medium"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_tg_subs_daily_filters", table_name="agg_tg_subs_daily")
    op.drop_index("idx_tg_subs_daily_group", table_name="agg_tg_subs_daily")
    op.drop_table("agg_tg_subs_daily")

