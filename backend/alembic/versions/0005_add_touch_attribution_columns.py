"""Add touch attribution columns to raw_bot_users."""

from alembic import op
import sqlalchemy as sa

revision = "0005_add_touch_attribution_columns"
down_revision = "0004_rebuild_agg_daily_new_users"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("raw_bot_users", sa.Column("first_touch_bot", sa.String(length=128)))
    op.add_column("raw_bot_users", sa.Column("first_touch_campaign", sa.String(length=128)))
    op.add_column("raw_bot_users", sa.Column("last_touch_bot", sa.String(length=128)))
    op.add_column("raw_bot_users", sa.Column("last_touch_campaign", sa.String(length=128)))


def downgrade() -> None:
    op.drop_column("raw_bot_users", "last_touch_campaign")
    op.drop_column("raw_bot_users", "last_touch_bot")
    op.drop_column("raw_bot_users", "first_touch_campaign")
    op.drop_column("raw_bot_users", "first_touch_bot")
