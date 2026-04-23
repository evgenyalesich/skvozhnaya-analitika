"""Add user_block to raw_bot_users.

Revision ID: 0010_add_user_block_to_raw_bot_users
Revises: 0009_add_ad_metrics_weekly
Create Date: 2026-02-04
"""

from alembic import op
import sqlalchemy as sa


revision = "0010_add_user_block_to_raw_bot_users"
down_revision = "0009_add_ad_metrics_weekly"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("raw_bot_users", sa.Column("user_block", sa.Boolean(), nullable=True))


def downgrade() -> None:
    op.drop_column("raw_bot_users", "user_block")
