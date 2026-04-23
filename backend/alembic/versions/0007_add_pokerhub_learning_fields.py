"""Add pokerhub learning fields to raw_bot_users."""

from alembic import op
import sqlalchemy as sa

revision = "0007_add_pokerhub_learning_fields"
down_revision = "0006_add_telegram_subscription_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("raw_bot_users", sa.Column("learn_start_date", sa.DateTime(timezone=True)))
    op.add_column("raw_bot_users", sa.Column("start_course", sa.String(length=32)))


def downgrade() -> None:
    op.drop_column("raw_bot_users", "start_course")
    op.drop_column("raw_bot_users", "learn_start_date")
