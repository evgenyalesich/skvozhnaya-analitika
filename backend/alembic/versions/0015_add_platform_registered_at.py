"""add platform_registered_at to raw_bot_users

Revision ID: 0015_add_platform_registered_at
Revises: 0014_add_distance_grinding
Create Date: 2026-02-07
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0015_add_platform_registered_at"
down_revision = "0014_add_distance_grinding"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("raw_bot_users", sa.Column("platform_registered_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("raw_bot_users", "platform_registered_at")
