"""Rebuild agg_daily_new_users into the modern schema."""

from alembic import op
import sqlalchemy as sa

revision = "0004_rebuild_agg_daily_new_users"
down_revision = "d172f22dd78d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("agg_daily_new_users")
    op.create_table(
        "agg_daily_new_users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("bot_key", sa.String(length=64)),
        sa.Column("utm_source", sa.String(length=128)),
        sa.Column("utm_campaign", sa.String(length=128)),
        sa.Column("advertising_company", sa.String(length=128)),
        sa.Column("users", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("budget", sa.Float(), nullable=False, server_default="0"),
        sa.Column("cac", sa.Float()),
    )
    op.create_index("idx_daily_bot_day", "agg_daily_new_users", ["bot_key", "day"])
    op.create_index("idx_daily_company_day", "agg_daily_new_users", ["advertising_company", "day"])


def downgrade() -> None:
    op.drop_index("idx_daily_company_day", table_name="agg_daily_new_users")
    op.drop_index("idx_daily_bot_day", table_name="agg_daily_new_users")
    op.drop_table("agg_daily_new_users")
    op.create_table(
        "agg_daily_new_users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("bot_key", sa.String(length=64)),
        sa.Column("utm_source", sa.String(length=128)),
        sa.Column("utm_campaign", sa.String(length=128)),
        sa.Column("advertising_company", sa.String(length=128)),
        sa.Column("users", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("budget", sa.Float(), nullable=False, server_default="0"),
        sa.Column("cac", sa.Float()),
    )
    op.create_index("idx_daily_bot_date", "agg_daily_new_users", ["bot_key", "date"])
    op.create_index("idx_daily_company", "agg_daily_new_users", ["advertising_company", "date"])
