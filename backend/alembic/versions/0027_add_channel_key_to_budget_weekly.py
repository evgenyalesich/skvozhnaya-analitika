"""add channel_key to budget_weekly

Revision ID: 0027_add_channel_key_to_budget_weekly
Revises: 0026_add_budget_weekly_period_and_utm
Create Date: 2026-03-30
"""
from alembic import op
import sqlalchemy as sa


revision = "0027_add_channel_key_to_budget_weekly"
down_revision = "0026_add_budget_weekly_period_and_utm"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("budget_weekly", sa.Column("channel_key", sa.String(length=32), nullable=True))
    op.create_index("ix_budget_weekly_channel_key", "budget_weekly", ["channel_key"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_budget_weekly_channel_key", table_name="budget_weekly")
    op.drop_column("budget_weekly", "channel_key")
