"""add contract stage dates to raw_bot_users

Revision ID: 0032_add_contract_stage_dates
Revises: 0031_add_replication_dlq
Create Date: 2026-04-25 11:20:00
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0032_add_contract_stage_dates"
down_revision = "0031_add_replication_dlq"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("raw_bot_users", sa.Column("interview_reached_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("raw_bot_users", sa.Column("interview_passed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("raw_bot_users", sa.Column("offer_received_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("raw_bot_users", sa.Column("contract_signed_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("raw_bot_users", "contract_signed_at")
    op.drop_column("raw_bot_users", "offer_received_at")
    op.drop_column("raw_bot_users", "interview_passed_at")
    op.drop_column("raw_bot_users", "interview_reached_at")
