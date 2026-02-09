"""create advertising companies tables

Revision ID: 0003_create_advertising_companies
Revises: 0002_create_bot_registry
Create Date: 2026-01-27
"""

from alembic import op
import sqlalchemy as sa


revision = "0003_create_advertising_companies"
down_revision = "0002_create_bot_registry"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("alembic_version", "version_num", type_=sa.String(length=64), existing_type=sa.String(length=32))
    op.create_table(
        "advertising_companies",
        sa.Column("company_id", sa.String(length=64), primary_key=True),
        sa.Column("company_name", sa.String(length=128), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_table(
        "advertising_company_bots",
        sa.Column("company_id", sa.String(length=64), sa.ForeignKey("advertising_companies.company_id", ondelete="CASCADE"), primary_key=True),
        sa.Column("bot_key", sa.String(length=64), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_unique_constraint("uq_advertising_company_bot", "advertising_company_bots", ["bot_key"])


def downgrade() -> None:
    op.drop_constraint("uq_advertising_company_bot", "advertising_company_bots", type_="unique")
    op.drop_table("advertising_company_bots")
    op.drop_table("advertising_companies")
