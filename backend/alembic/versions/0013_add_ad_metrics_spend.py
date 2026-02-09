"""add spend to ad_metrics_weekly

Revision ID: 0013_add_ad_metrics_spend
Revises: 0012_add_system_settings_and_sync_logs
Create Date: 2026-02-05
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0013_add_ad_metrics_spend"
down_revision = "0012_add_system_settings_and_sync_logs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "ad_metrics_weekly",
        sa.Column("spend", sa.Float(), nullable=False, server_default="0"),
    )
    op.alter_column("ad_metrics_weekly", "spend", server_default=None)


def downgrade() -> None:
    op.drop_column("ad_metrics_weekly", "spend")
