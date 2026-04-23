"""add platform utm columns to raw_bot_users

Revision ID: 0021_add_platform_utm_columns
Revises: 0020_add_replicate_to_bot_registry
Create Date: 2026-03-25
"""

from alembic import op
import sqlalchemy as sa


revision = "0021_add_platform_utm_columns"
down_revision = "0020_add_replicate_to_bot_registry"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("raw_bot_users", sa.Column("platform_utm_source", sa.String(length=128), nullable=True))
    op.add_column("raw_bot_users", sa.Column("platform_utm_campaign", sa.String(length=128), nullable=True))
    op.add_column("raw_bot_users", sa.Column("platform_utm_medium", sa.String(length=128), nullable=True))
    op.add_column("raw_bot_users", sa.Column("platform_utm_content", sa.String(length=256), nullable=True))
    op.add_column("raw_bot_users", sa.Column("platform_utm_term", sa.String(length=256), nullable=True))
    op.create_index("ix_raw_bot_users_platform_utm_source", "raw_bot_users", ["platform_utm_source"], unique=False)
    op.create_index("ix_raw_bot_users_platform_utm_campaign", "raw_bot_users", ["platform_utm_campaign"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_raw_bot_users_platform_utm_campaign", table_name="raw_bot_users")
    op.drop_index("ix_raw_bot_users_platform_utm_source", table_name="raw_bot_users")
    op.drop_column("raw_bot_users", "platform_utm_term")
    op.drop_column("raw_bot_users", "platform_utm_content")
    op.drop_column("raw_bot_users", "platform_utm_medium")
    op.drop_column("raw_bot_users", "platform_utm_campaign")
    op.drop_column("raw_bot_users", "platform_utm_source")
