"""add period and utm columns to budget_weekly

Revision ID: 0026_add_budget_weekly_period_and_utm
Revises: 0025_add_marketing_daily_settings
Create Date: 2026-03-29
"""
from alembic import op
import sqlalchemy as sa


revision = "0026_add_budget_weekly_period_and_utm"
down_revision = "0025_add_marketing_daily_settings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("budget_weekly", sa.Column("period_end", sa.Date(), nullable=True))
    op.add_column("budget_weekly", sa.Column("utm_source", sa.String(length=128), nullable=True))
    op.add_column("budget_weekly", sa.Column("utm_campaign", sa.String(length=128), nullable=True))
    op.add_column("budget_weekly", sa.Column("utm_medium", sa.String(length=128), nullable=True))
    op.add_column("budget_weekly", sa.Column("utm_content", sa.String(length=256), nullable=True))
    op.add_column("budget_weekly", sa.Column("utm_term", sa.String(length=256), nullable=True))

    op.execute("UPDATE budget_weekly SET period_end = week_start WHERE period_end IS NULL")

    op.create_index("ix_budget_weekly_utm_source", "budget_weekly", ["utm_source"], unique=False)
    op.create_index("ix_budget_weekly_utm_campaign", "budget_weekly", ["utm_campaign"], unique=False)
    op.create_index("ix_budget_weekly_utm_medium", "budget_weekly", ["utm_medium"], unique=False)
    op.create_index(
        "idx_budget_weekly_utm_combo",
        "budget_weekly",
        ["week_start", "utm_source", "utm_campaign", "utm_medium"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_budget_weekly_utm_combo", table_name="budget_weekly")
    op.drop_index("ix_budget_weekly_utm_medium", table_name="budget_weekly")
    op.drop_index("ix_budget_weekly_utm_campaign", table_name="budget_weekly")
    op.drop_index("ix_budget_weekly_utm_source", table_name="budget_weekly")

    op.drop_column("budget_weekly", "utm_term")
    op.drop_column("budget_weekly", "utm_content")
    op.drop_column("budget_weekly", "utm_medium")
    op.drop_column("budget_weekly", "utm_campaign")
    op.drop_column("budget_weekly", "utm_source")
    op.drop_column("budget_weekly", "period_end")
