"""add channel_subscribed_at to raw_bot_users

Revision ID: 0033_add_channel_subscribed_at
Revises: 0032_add_contract_stage_dates
Create Date: 2026-04-25 12:00:00
"""

from alembic import op
import sqlalchemy as sa


revision = "0033_add_channel_subscribed_at"
down_revision = "0032_add_contract_stage_dates"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "raw_bot_users",
        sa.Column("channel_subscribed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("raw_bot_users", "channel_subscribed_at")
