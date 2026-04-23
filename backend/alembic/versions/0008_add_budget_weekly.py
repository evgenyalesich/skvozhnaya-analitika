"""Add weekly budgets table."""

from alembic import op
import sqlalchemy as sa

revision = "0008_add_budget_weekly"
down_revision = "0007_add_pokerhub_learning_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "budget_weekly",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("week_start", sa.Date(), nullable=False),
        sa.Column("campaign", sa.String(length=128), nullable=False),
        sa.Column("bot_key", sa.String(length=64)),
        sa.Column("amount", sa.Float(), nullable=False, server_default="0"),
        sa.Column("currency", sa.String(length=8), nullable=False, server_default="USD"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_budget_weekly_campaign_week", "budget_weekly", ["campaign", "week_start"])
    op.create_index("ix_budget_weekly_week_start", "budget_weekly", ["week_start"])
    op.create_index("ix_budget_weekly_campaign", "budget_weekly", ["campaign"])


def downgrade() -> None:
    op.drop_index("ix_budget_weekly_campaign", table_name="budget_weekly")
    op.drop_index("ix_budget_weekly_week_start", table_name="budget_weekly")
    op.drop_index("idx_budget_weekly_campaign_week", table_name="budget_weekly")
    op.drop_table("budget_weekly")
