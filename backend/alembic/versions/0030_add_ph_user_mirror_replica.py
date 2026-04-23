"""add ph_user_mirror_replica and lead_user_id

Revision ID: 0030_add_ph_user_mirror_replica
Revises: 0029_add_ph_mirror_context_columns
Create Date: 2026-04-21
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0030_add_ph_user_mirror_replica"
down_revision = "0029_add_ph_mirror_context_columns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("raw_bot_users", sa.Column("lead_user_id", sa.BigInteger(), nullable=True))
    op.create_index("idx_raw_lead_user_id", "raw_bot_users", ["lead_user_id"], unique=False)

    op.create_table(
        "ph_user_mirror_replica",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("ph_id", sa.String(length=255), nullable=True),
        sa.Column("username", sa.String(length=255), nullable=True),
        sa.Column("first_name", sa.String(length=255), nullable=True),
        sa.Column("last_name", sa.String(length=255), nullable=True),
        sa.Column("ph_registration", sa.String(length=32), nullable=True),
        sa.Column("ph_registration_at", sa.String(length=64), nullable=True),
        sa.Column("authorization_date", sa.String(length=32), nullable=True),
        sa.Column("last_activity", sa.String(length=64), nullable=True),
        sa.Column("last_visit_date", sa.String(length=64), nullable=True),
        sa.Column("is_blocked", sa.Boolean(), nullable=True),
        sa.Column("utm", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("ph_utm", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("referer", sa.Text(), nullable=True),
        sa.Column("raw_link", sa.Text(), nullable=True),
        sa.Column("bot_raw", sa.Text(), nullable=True),
        sa.Column("ph_raw", sa.Text(), nullable=True),
        sa.Column("rc", sa.String(length=255), nullable=True),
        sa.Column("group", sa.String(length=255), nullable=True),
        sa.Column("groups", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("courses", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("lessons", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("course_memberships", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("custom_tests", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("source_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_ph_user_mirror_replica_ph_id", "ph_user_mirror_replica", ["ph_id"], unique=False)
    op.create_index("ix_ph_user_mirror_replica_username", "ph_user_mirror_replica", ["username"], unique=False)
    op.create_index("ix_ph_user_mirror_replica_ph_registration", "ph_user_mirror_replica", ["ph_registration"], unique=False)
    op.create_index("ix_ph_user_mirror_replica_last_activity", "ph_user_mirror_replica", ["last_activity"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_ph_user_mirror_replica_last_activity", table_name="ph_user_mirror_replica")
    op.drop_index("ix_ph_user_mirror_replica_ph_registration", table_name="ph_user_mirror_replica")
    op.drop_index("ix_ph_user_mirror_replica_username", table_name="ph_user_mirror_replica")
    op.drop_index("ix_ph_user_mirror_replica_ph_id", table_name="ph_user_mirror_replica")
    op.drop_table("ph_user_mirror_replica")
    op.drop_index("idx_raw_lead_user_id", table_name="raw_bot_users")
    op.drop_column("raw_bot_users", "lead_user_id")
