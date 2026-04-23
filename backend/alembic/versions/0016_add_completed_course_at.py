"""add completed_course_at to raw_bot_users

Revision ID: 0016_add_completed_course_at
Revises: 0015_add_platform_registered_at
Create Date: 2026-02-27
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0016_add_completed_course_at"
down_revision = "0015_add_platform_registered_at"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("raw_bot_users", sa.Column("completed_course_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("raw_bot_users", "completed_course_at")

