"""Add telegram subscription events table."""

from alembic import op
import sqlalchemy as sa

revision = "0006_add_telegram_subscription_events"
down_revision = "0005_add_touch_attribution_columns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "telegram_subscription_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tg_user_id", sa.BigInteger(), nullable=False),
        sa.Column("channel_id", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index(
        "idx_telegram_sub_event_user_channel",
        "telegram_subscription_events",
        ["tg_user_id", "channel_id"],
    )
    op.create_index(
        "idx_telegram_sub_event_checked_at",
        "telegram_subscription_events",
        ["checked_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_telegram_sub_event_checked_at", table_name="telegram_subscription_events")
    op.drop_index("idx_telegram_sub_event_user_channel", table_name="telegram_subscription_events")
    op.drop_table("telegram_subscription_events")
