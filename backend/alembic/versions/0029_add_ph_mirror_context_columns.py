"""add curated ph mirror context columns to raw_bot_users

Revision ID: 0029_add_ph_mirror_context_columns
Revises: 0028_add_ph_user_id
Create Date: 2026-04-21
"""
from alembic import op
import sqlalchemy as sa


revision = "0029_add_ph_mirror_context_columns"
down_revision = "0028_add_ph_user_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("raw_bot_users", sa.Column("referer", sa.Text(), nullable=True))
    op.add_column("raw_bot_users", sa.Column("raw_link", sa.Text(), nullable=True))
    op.add_column("raw_bot_users", sa.Column("bot_raw", sa.Text(), nullable=True))
    op.add_column("raw_bot_users", sa.Column("ph_raw", sa.Text(), nullable=True))
    op.add_column("raw_bot_users", sa.Column("last_activity", sa.String(length=64), nullable=True))
    op.add_column("raw_bot_users", sa.Column("ph_group", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("raw_bot_users", "ph_group")
    op.drop_column("raw_bot_users", "last_activity")
    op.drop_column("raw_bot_users", "ph_raw")
    op.drop_column("raw_bot_users", "bot_raw")
    op.drop_column("raw_bot_users", "raw_link")
    op.drop_column("raw_bot_users", "referer")
