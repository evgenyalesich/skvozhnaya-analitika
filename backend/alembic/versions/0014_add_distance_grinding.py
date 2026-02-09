"""add distance_grinding to raw_bot_users

Revision ID: 0014_add_distance_grinding
Revises: 0013_add_ad_metrics_spend
Create Date: 2026-02-07
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0014_add_distance_grinding"
down_revision = "0013_add_ad_metrics_spend"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "raw_bot_users",
        sa.Column("distance_grinding", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.alter_column("raw_bot_users", "distance_grinding", server_default=None)


def downgrade() -> None:
    op.drop_column("raw_bot_users", "distance_grinding")
