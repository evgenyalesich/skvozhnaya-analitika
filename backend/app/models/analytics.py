from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import func
from sqlalchemy.dialects.postgresql import BIGINT

from ..db.base import Base


class RawBotUser(Base):
    __tablename__ = "raw_bot_users"
    id = Column(Integer, primary_key=True, index=True)
    bot_key = Column(String(64), nullable=False, index=True)
    tg_user_id = Column(BIGINT, nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=func.now())
    ingested_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    utm_source = Column(String(128), index=True)
    utm_campaign = Column(String(128), index=True)
    utm_medium = Column(String(128))
    utm_content = Column(String(256))
    utm_term = Column(String(256))

    advertising_company = Column(String(128), index=True)
    budget = Column(Float, default=0.0)

    converted_to_lead = Column(Boolean, default=False)
    registered_platform = Column(Boolean, default=False)
    started_learning = Column(Boolean, default=False)
    completed_course = Column(Boolean, default=False)
    used_simulator = Column(Boolean, default=False)
    interview_reached = Column(Boolean, default=False)
    interview_passed = Column(Boolean, default=False)
    offer_received = Column(Boolean, default=False)
    contract_signed = Column(Boolean, default=False)

    channel_subscribed = Column(Boolean, default=False)
    community_member = Column(Boolean, default=False)
    team_member = Column(Boolean, default=False)
    internal_status = Column(Text)

    __table_args__ = (
        UniqueConstraint("bot_key", "tg_user_id", name="uq_bot_user"),
        Index("idx_raw_utm_combo", "utm_source", "utm_campaign"),
    )


class DailyNewUsersAgg(Base):
    __tablename__ = "agg_daily_new_users"
    id = Column(Integer, primary_key=True)
    date = Column(Date, nullable=False, index=True)
    bot_key = Column(String(64))
    utm_source = Column(String(128))
    utm_campaign = Column(String(128))
    advertising_company = Column(String(128))
    users = Column(Integer, nullable=False, default=0)
    budget = Column(Float, nullable=False, default=0.0)
    cac = Column(Float)

    __table_args__ = (
        Index("idx_daily_bot_date", "bot_key", "date"),
        Index("idx_daily_company", "advertising_company", "date"),
    )
