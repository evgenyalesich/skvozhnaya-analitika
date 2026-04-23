"""add ph_user_id to raw_bot_users

Revision ID: 0028_add_ph_user_id
Revises: 0027_add_channel_key_to_budget_weekly
Create Date: 2026-04-15
"""
from alembic import op
import sqlalchemy as sa


revision = "0028_add_ph_user_id"
down_revision = "0027_add_channel_key_to_budget_weekly"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("raw_bot_users", sa.Column("ph_user_id", sa.Integer(), nullable=True))
    op.create_index("ix_raw_bot_users_ph_user_id", "raw_bot_users", ["ph_user_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_raw_bot_users_ph_user_id", table_name="raw_bot_users")
    op.drop_column("raw_bot_users", "ph_user_id")
