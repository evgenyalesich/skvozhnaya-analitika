"""add platform to advertising_companies

Revision ID: 0019_add_platform_to_advertising_companies
Revises: 0018_add_employee_registry
Create Date: 2026-03-18 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "0019_add_platform_to_advertising_companies"
down_revision = "0018_add_employee_registry"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "advertising_companies",
        sa.Column("platform", sa.String(128), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("advertising_companies", "platform")
