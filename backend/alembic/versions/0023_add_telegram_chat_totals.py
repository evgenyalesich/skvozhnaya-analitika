"""add telegram chat totals

Revision ID: 0023_add_telegram_chat_totals
Revises: 0022_add_telegram_chat_memberships
Create Date: 2026-03-26
"""

from alembic import op
import sqlalchemy as sa


revision = "0023_add_telegram_chat_totals"
down_revision = "0022_add_telegram_chat_memberships"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "telegram_chat_totals",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("chat_id", sa.String(length=64), nullable=False),
        sa.Column("participants_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("source", sa.String(length=32), nullable=False, server_default=sa.text("'full_sync'")),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("chat_id", name="uq_telegram_chat_total_chat_id"),
    )
    op.create_index("ix_telegram_chat_totals_chat_id", "telegram_chat_totals", ["chat_id"], unique=True)
    op.create_index(
        "idx_telegram_chat_total_observed_at",
        "telegram_chat_totals",
        ["observed_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_telegram_chat_total_observed_at", table_name="telegram_chat_totals")
    op.drop_index("ix_telegram_chat_totals_chat_id", table_name="telegram_chat_totals")
    op.drop_table("telegram_chat_totals")
