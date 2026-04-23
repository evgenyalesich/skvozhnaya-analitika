"""add marketing daily settings key

Revision ID: 0025
Revises: 0024_add_utm_rules_to_advertising_companies
Create Date: 2026-03-28
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0025_add_marketing_daily_settings"
down_revision = "0024_add_utm_rules_to_advertising_companies"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.get_bind().execute(
        sa.text(
            """
            INSERT INTO system_settings (key, value)
            VALUES (
              'marketing_daily',
              CAST(:marketing_daily_value AS jsonb)
            )
            ON CONFLICT (key) DO NOTHING
            """
        ),
        {
            "marketing_daily_value": '{"enabled": true, "send_hour_msk": 9, "show_top_growth": 3, "show_top_decline": 3, "allowed_subscriber_ids": [], "anomaly_drop_threshold_pct": -50.0, "downward_streak_days": 3, "send_data_warning_alerts": true}'
        },
    )


def downgrade() -> None:
    op.execute("DELETE FROM system_settings WHERE key = 'marketing_daily'")
