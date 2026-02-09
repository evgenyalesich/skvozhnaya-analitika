"""add system settings and sync logs

Revision ID: 0012_add_system_settings_and_sync_logs
Revises: 0011_add_agg_tg_subs_daily
Create Date: 2026-02-05 00:30:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "0012_add_system_settings_and_sync_logs"
down_revision = "0011_add_agg_tg_subs_daily"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "system_settings",
        sa.Column("key", sa.String(length=64), primary_key=True),
        sa.Column("value", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.create_table(
        "sync_event_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("level", sa.String(length=16), nullable=False),
        sa.Column("message", sa.String(length=1024), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("idx_sync_event_logs_created_at", "sync_event_logs", ["created_at"])


def downgrade() -> None:
    op.drop_index("idx_sync_event_logs_created_at", table_name="sync_event_logs")
    op.drop_table("sync_event_logs")
    op.drop_table("system_settings")
