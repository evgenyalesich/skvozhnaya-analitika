"""create bot_registry

Revision ID: 0002_create_bot_registry
Revises: 0001_create_analytics_schema
Create Date: 2026-01-27
"""

from alembic import op
import sqlalchemy as sa


revision = "0002_create_bot_registry"
down_revision = "0001_create_analytics_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "bot_registry",
        sa.Column("bot_key", sa.String(length=64), primary_key=True),
        sa.Column("display_name", sa.String(length=128), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("bot_registry")
