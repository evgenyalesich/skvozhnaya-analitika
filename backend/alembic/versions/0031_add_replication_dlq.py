"""add replication dlq table

Revision ID: 0031_add_replication_dlq
Revises: 0030_add_ph_user_mirror_replica
Create Date: 2026-04-25
"""
from alembic import op
import sqlalchemy as sa


revision = "0031_add_replication_dlq"
down_revision = "0030_add_ph_user_mirror_replica"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "replication_dlq",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("db_name", sa.String(length=128), nullable=False),
        sa.Column("bot_key", sa.String(length=128), nullable=False),
        sa.Column("reason", sa.String(length=128), nullable=False),
        sa.Column("payload", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_replication_dlq_created_at", "replication_dlq", ["created_at"], unique=False)
    op.create_index("ix_replication_dlq_db_name", "replication_dlq", ["db_name"], unique=False)
    op.create_index("ix_replication_dlq_bot_key", "replication_dlq", ["bot_key"], unique=False)
    op.create_index("ix_replication_dlq_reason", "replication_dlq", ["reason"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_replication_dlq_reason", table_name="replication_dlq")
    op.drop_index("ix_replication_dlq_bot_key", table_name="replication_dlq")
    op.drop_index("ix_replication_dlq_db_name", table_name="replication_dlq")
    op.drop_index("idx_replication_dlq_created_at", table_name="replication_dlq")
    op.drop_table("replication_dlq")
