"""Add weekly ad metrics table."""

from alembic import op
import sqlalchemy as sa

revision = "0009_add_ad_metrics_weekly"
down_revision = "0008_add_budget_weekly"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ad_metrics_weekly",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("week_start", sa.Date(), nullable=False),
        sa.Column("campaign", sa.String(length=128), nullable=False),
        sa.Column("bot_key", sa.String(length=64)),
        sa.Column("impressions", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("clicks", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_ad_metrics_weekly_campaign_week", "ad_metrics_weekly", ["campaign", "week_start"])
    op.create_index("ix_ad_metrics_weekly_week_start", "ad_metrics_weekly", ["week_start"])
    op.create_index("ix_ad_metrics_weekly_campaign", "ad_metrics_weekly", ["campaign"])


def downgrade() -> None:
    op.drop_index("ix_ad_metrics_weekly_campaign", table_name="ad_metrics_weekly")
    op.drop_index("ix_ad_metrics_weekly_week_start", table_name="ad_metrics_weekly")
    op.drop_index("idx_ad_metrics_weekly_campaign_week", table_name="ad_metrics_weekly")
    op.drop_table("ad_metrics_weekly")
