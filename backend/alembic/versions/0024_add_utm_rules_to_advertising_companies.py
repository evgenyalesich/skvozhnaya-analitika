"""add utm_rules to advertising_companies

Revision ID: 0024
Revises: 0023
Create Date: 2026-03-28
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0024_add_utm_rules_to_advertising_companies"
down_revision = "0023_add_telegram_chat_totals"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "advertising_companies",
        sa.Column("utm_rules", JSONB, nullable=False, server_default="[]"),
    )


def downgrade() -> None:
    op.drop_column("advertising_companies", "utm_rules")
