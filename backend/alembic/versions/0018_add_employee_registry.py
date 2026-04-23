"""add employee registry

Revision ID: 0018_add_employee_registry
Revises: 0017_add_canonical_base_to_bot_registry
Create Date: 2026-02-28 22:20:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "0018_add_employee_registry"
down_revision = "0017_add_canonical_base_to_bot_registry"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "employee_registry",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tg_user_id", postgresql.BIGINT(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", sa.String(length=128), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_employee_registry_tg_user_id"), "employee_registry", ["tg_user_id"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_employee_registry_tg_user_id"), table_name="employee_registry")
    op.drop_table("employee_registry")
