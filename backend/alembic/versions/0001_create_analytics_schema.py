"""create analytics schema"""

from alembic import op
import sqlalchemy as sa

revision = "0001_create_analytics_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "raw_bot_users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("bot_key", sa.String(length=64), nullable=False),
        sa.Column("tg_user_id", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("utm_source", sa.String(length=128)),
        sa.Column("utm_campaign", sa.String(length=128)),
        sa.Column("utm_medium", sa.String(length=128)),
        sa.Column("utm_content", sa.String(length=256)),
        sa.Column("utm_term", sa.String(length=256)),
        sa.Column("advertising_company", sa.String(length=128)),
        sa.Column("budget", sa.Float(), nullable=False, server_default="0"),
        sa.Column("converted_to_lead", sa.Boolean(), nullable=False, server_default=sa.text("FALSE")),
        sa.Column("registered_platform", sa.Boolean(), nullable=False, server_default=sa.text("FALSE")),
        sa.Column("started_learning", sa.Boolean(), nullable=False, server_default=sa.text("FALSE")),
        sa.Column("completed_course", sa.Boolean(), nullable=False, server_default=sa.text("FALSE")),
        sa.Column("used_simulator", sa.Boolean(), nullable=False, server_default=sa.text("FALSE")),
        sa.Column("interview_reached", sa.Boolean(), nullable=False, server_default=sa.text("FALSE")),
        sa.Column("interview_passed", sa.Boolean(), nullable=False, server_default=sa.text("FALSE")),
        sa.Column("offer_received", sa.Boolean(), nullable=False, server_default=sa.text("FALSE")),
        sa.Column("contract_signed", sa.Boolean(), nullable=False, server_default=sa.text("FALSE")),
        sa.Column("channel_subscribed", sa.Boolean(), nullable=False, server_default=sa.text("FALSE")),
        sa.Column("community_member", sa.Boolean(), nullable=False, server_default=sa.text("FALSE")),
        sa.Column("team_member", sa.Boolean(), nullable=False, server_default=sa.text("FALSE")),
        sa.Column("internal_status", sa.Text()),
        sa.UniqueConstraint("bot_key", "tg_user_id", name="uq_bot_user"),
    )
    op.create_index("idx_raw_bot_key", "raw_bot_users", ["bot_key"])
    op.create_index("idx_raw_tg_user", "raw_bot_users", ["tg_user_id"])
    op.create_index("idx_raw_created", "raw_bot_users", ["created_at"])
    op.create_index("idx_raw_utm_source", "raw_bot_users", ["utm_source"])
    op.create_index("idx_raw_utm_campaign", "raw_bot_users", ["utm_campaign"])
    op.create_index("idx_raw_company", "raw_bot_users", ["advertising_company"])

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


def downgrade() -> None:
    op.drop_table("agg_daily_new_users")
    op.drop_index("idx_raw_company", table_name="raw_bot_users")
    op.drop_index("idx_raw_utm_campaign", table_name="raw_bot_users")
    op.drop_index("idx_raw_utm_source", table_name="raw_bot_users")
    op.drop_index("idx_raw_created", table_name="raw_bot_users")
    op.drop_index("idx_raw_tg_user", table_name="raw_bot_users")
    op.drop_index("idx_raw_bot_key", table_name="raw_bot_users")
    op.drop_table("raw_bot_users")
