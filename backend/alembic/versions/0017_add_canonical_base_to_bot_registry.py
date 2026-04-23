"""add canonical_base to bot_registry

Revision ID: 0017_add_canonical_base_to_bot_registry
Revises: 0016_add_completed_course_at
Create Date: 2026-02-28
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0017_add_canonical_base_to_bot_registry"
down_revision = "0016_add_completed_course_at"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("bot_registry", sa.Column("canonical_base", sa.String(length=128), nullable=True))
    op.execute("UPDATE bot_registry SET canonical_base = COALESCE(NULLIF(display_name, ''), bot_key)")


def downgrade() -> None:
    op.drop_column("bot_registry", "canonical_base")
