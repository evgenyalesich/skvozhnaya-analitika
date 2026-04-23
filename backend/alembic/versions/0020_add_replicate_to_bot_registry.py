"""add replicate to bot_registry

Revision ID: 0020_add_replicate_to_bot_registry
Revises: 0019_add_platform_to_advertising_companies
Create Date: 2026-03-22 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "0020_add_replicate_to_bot_registry"
down_revision = "0019_add_platform_to_advertising_companies"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "bot_registry",
        sa.Column("replicate", sa.Boolean(), nullable=False, server_default=sa.true()),
    )


def downgrade() -> None:
    op.drop_column("bot_registry", "replicate")
