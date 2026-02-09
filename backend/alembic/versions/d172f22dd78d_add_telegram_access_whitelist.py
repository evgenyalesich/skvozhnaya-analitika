"""Add telegram access whitelist

Revision ID: d172f22dd78d
Revises: 0003_create_advertising_companies
Create Date: 2026-01-30 01:48:46.415318

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'd172f22dd78d'
down_revision = '0003_create_advertising_companies'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "telegram_access",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tg_user_id", sa.BigInteger(), nullable=False, unique=True, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("created_by", sa.String(length=128)),
    )


def downgrade() -> None:
    op.drop_table("telegram_access")
