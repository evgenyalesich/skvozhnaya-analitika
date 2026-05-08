from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy import func
from sqlalchemy.dialects.postgresql import BIGINT, JSONB

from ..db.base import Base

# Все SQLAlchemy-модели проекта (таблицы в PostgreSQL).
# Каждый класс = одна таблица. Миграции в alembic/versions/.


class RawBotUser(Base):
    """Сырые данные пользователей Telegram-ботов.

    Основная рабочая таблица — один ряд на пару (bot_key, tg_user_id).
    Хранит весь путь пользователя по воронке: от первого старта бота
    до подписания контракта. UTM-метки дублируются в двух наборах:
    bot-UTM (откуда пришёл в бот) и platform-UTM (откуда пришёл на платформу).
    """
    __tablename__ = "raw_bot_users"
    id = Column(Integer, primary_key=True, index=True)
    bot_key = Column(String(64), nullable=False, index=True)
    tg_user_id = Column(BIGINT, nullable=False, index=True)
    username = Column(String(128), index=True)
    user_block = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=func.now())
    ingested_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    utm_source = Column(String(128), index=True)
    utm_campaign = Column(String(128), index=True)
    utm_medium = Column(String(128))
    utm_content = Column(String(256))
    utm_term = Column(String(256))
    platform_utm_source = Column(String(128), index=True)
    platform_utm_campaign = Column(String(128), index=True)
    platform_utm_medium = Column(String(128))
    platform_utm_content = Column(String(256))
    platform_utm_term = Column(String(256))

    advertising_company = Column(String(128), index=True)
    budget = Column(Float, default=0.0)

    converted_to_lead = Column(Boolean, default=False)
    registered_platform = Column(Boolean, default=False)
    platform_registered_at = Column(DateTime(timezone=True))
    started_learning = Column(Boolean, default=False)
    completed_course = Column(Boolean, default=False)
    completed_course_at = Column(DateTime(timezone=True))
    used_simulator = Column(Boolean, default=False)
    interview_reached = Column(Boolean, default=False)
    interview_passed = Column(Boolean, default=False)
    offer_received = Column(Boolean, default=False)
    contract_signed = Column(Boolean, default=False)
    interview_reached_at = Column(DateTime(timezone=True))
    interview_passed_at = Column(DateTime(timezone=True))
    offer_received_at = Column(DateTime(timezone=True))
    contract_signed_at = Column(DateTime(timezone=True))
    distance_grinding = Column(Boolean, default=False)
    interview_reached_status = Column(Text)
    interview_passed_status = Column(Text)
    offer_received_status = Column(Text)
    contract_signed_status = Column(Text)
    community_member_status = Column(Text)

    channel_subscribed = Column(Boolean, default=False)
    channel_subscribed_at = Column(DateTime(timezone=True))
    community_member = Column(Boolean, default=False)
    team_member = Column(Boolean, default=False)
    internal_status = Column(Text)

    learn_start_date = Column(DateTime(timezone=True))
    start_course = Column(String(32))
    ph_user_id = Column(Integer, index=True)
    lead_user_id = Column(BIGINT, index=True)
    referer = Column(Text)
    raw_link = Column(Text)
    bot_raw = Column(Text)
    ph_raw = Column(Text)
    last_activity = Column(String(64))
    ph_group = Column(String(255))

    first_touch_bot = Column(String(128))
    first_touch_campaign = Column(String(128))
    last_touch_bot = Column(String(128))
    last_touch_campaign = Column(String(128))

    __table_args__ = (
        UniqueConstraint("bot_key", "tg_user_id", name="uq_bot_user"),
        Index("idx_raw_utm_combo", "utm_source", "utm_campaign"),
        Index("idx_raw_created_tg", "created_at", "tg_user_id"),
        Index("idx_raw_bot_created", "bot_key", "created_at"),
        Index("idx_raw_company_created", "advertising_company", "created_at"),
        Index("idx_raw_tg_created", "tg_user_id", "created_at"),
        Index(
            "idx_raw_learn_start_tg",
            "learn_start_date",
            "tg_user_id",
            postgresql_where=text("learn_start_date IS NOT NULL"),
        ),
        Index("idx_raw_first_touch_tg", "first_touch_bot", "tg_user_id"),
        Index("idx_raw_last_touch_tg", "last_touch_bot", "tg_user_id"),
        Index("idx_raw_lead_user_id", "lead_user_id"),
    )


class PhUserMirrorReplica(Base):
    """Зеркало пользователей с платформы PokerHub.

    Реплицируется из внешней БД через replication_worker.
    Хранит актуальный снимок: группы, курсы, уроки, UTM.
    source_updated_at — время обновления в источнике,
    synced_at — время последней репликации сюда.
    """
    __tablename__ = "ph_user_mirror_replica"

    id = Column(BIGINT, primary_key=True)
    ph_id = Column(String(255), index=True)
    username = Column(String(255), index=True)
    first_name = Column(String(255))
    last_name = Column(String(255))
    ph_registration = Column(String(32), index=True)
    ph_registration_at = Column(String(64))
    authorization_date = Column(String(32))
    last_activity = Column(String(64), index=True)
    last_visit_date = Column(String(64))
    is_blocked = Column(Boolean)
    utm = Column(JSONB, nullable=False, server_default="{}")
    ph_utm = Column(JSONB, nullable=False, server_default="{}")
    referer = Column(Text)
    raw_link = Column(Text)
    bot_raw = Column(Text)
    ph_raw = Column(Text)
    rc = Column(String(255))
    ph_group = Column("group", String(255))
    groups = Column(JSONB, nullable=False, server_default="[]")
    courses = Column(JSONB, nullable=False, server_default="{}")
    lessons = Column(JSONB, nullable=False, server_default="[]")
    course_memberships = Column(JSONB, nullable=False, server_default="[]")
    custom_tests = Column(JSONB, nullable=False, server_default="[]")
    source_updated_at = Column(DateTime(timezone=True))
    synced_at = Column(DateTime(timezone=True))


class DailyNewUsersAgg(Base):
    """Агрегат: новые пользователи по дням.

    Заполняется aggregate_refresher. Одна строка = один день + разбивка
    по bot_key / utm / advertising_company. Используется в дашборде
    для графика новых пользователей и расчёта CAC.
    """
    __tablename__ = "agg_daily_new_users"
    id = Column(Integer, primary_key=True)
    day = Column(Date, nullable=False, index=True)
    bot_key = Column(String(64))
    utm_source = Column(String(128))
    utm_campaign = Column(String(128))
    advertising_company = Column(String(128))
    users = Column(Integer, nullable=False, default=0)
    budget = Column(Float, nullable=False, default=0.0)
    cac = Column(Float)

    __table_args__ = (
        Index("idx_daily_bot_day", "bot_key", "day"),
        Index("idx_daily_company", "advertising_company", "day"),
    )


class TgSubsDailyAgg(Base):
    """Агрегат: подписки/отписки Telegram-каналов по дням.

    Счётчики bot_starts, almanah_starts, channel_subscribed/unsubscribed,
    saloon_subscribed/unsubscribed сгруппированы по дню + UTM-измерениям.
    Используется в отчёте по Telegram-подпискам.
    """
    __tablename__ = "agg_tg_subs_daily"
    id = Column(Integer, primary_key=True)
    day = Column(Date, nullable=False, index=True)
    campaign = Column(String(128), nullable=False, default="", index=True)
    bot_key = Column(String(64), nullable=False, default="", index=True)
    advertising_company = Column(String(128), nullable=False, default="", index=True)
    utm_source = Column(String(128), nullable=False, default="", index=True)
    utm_campaign = Column(String(128), nullable=False, default="", index=True)
    utm_medium = Column(String(128), nullable=False, default="", index=True)
    utm_content = Column(String(256), nullable=False, default="")
    utm_term = Column(String(256), nullable=False, default="")
    bot_starts = Column(Integer, nullable=False, default=0)
    almanah_starts = Column(Integer, nullable=False, default=0)
    channel_subscribed = Column(Integer, nullable=False, default=0)
    channel_unsubscribed = Column(Integer, nullable=False, default=0)
    saloon_subscribed = Column(Integer, nullable=False, default=0)
    saloon_unsubscribed = Column(Integer, nullable=False, default=0)

    __table_args__ = (
        Index("idx_tg_subs_daily_group", "day", "campaign"),
        Index("idx_tg_subs_daily_filters", "day", "bot_key", "advertising_company", "utm_source", "utm_campaign", "utm_medium"),
        UniqueConstraint(
            "day",
            "campaign",
            "bot_key",
            "advertising_company",
            "utm_source",
            "utm_campaign",
            "utm_medium",
            "utm_content",
            "utm_term",
            name="uq_tg_subs_daily_dimensions",
        ),
    )


class WeeklyFunnelBotAgg(Base):
    """Агрегат: воронка по неделям в разбивке по боту.

    Каждый этап воронки (entered → contract) — отдельный счётчик.
    Одна строка = неделя + bot_key.
    """
    __tablename__ = "agg_weekly_funnel_bot"
    id = Column(Integer, primary_key=True)
    week_start = Column(Date, nullable=False, index=True)
    bot_key = Column(String(64), nullable=False)
    entered = Column(Integer, nullable=False, default=0)
    new_in_system = Column(Integer, nullable=False, default=0)
    old_in_system = Column(Integer, nullable=False, default=0)
    lead = Column(Integer, nullable=False, default=0)
    subscribed = Column(Integer, nullable=False, default=0)
    platform = Column(Integer, nullable=False, default=0)
    learning = Column(Integer, nullable=False, default=0)
    course = Column(Integer, nullable=False, default=0)
    simulator = Column(Integer, nullable=False, default=0)
    interview = Column(Integer, nullable=False, default=0)
    passed = Column(Integer, nullable=False, default=0)
    offer = Column(Integer, nullable=False, default=0)
    contract = Column(Integer, nullable=False, default=0)
    distance_grinding = Column(Integer, nullable=False, default=0)

    __table_args__ = (
        UniqueConstraint("week_start", "bot_key", name="uq_weekly_funnel_bot"),
        Index("idx_weekly_funnel_bot_lookup", "bot_key", "week_start"),
    )


class WeeklyFunnelCompanyAgg(Base):
    """Агрегат: воронка по неделям в разбивке по рекламной компании.

    Аналог WeeklyFunnelBotAgg, но группировка по advertising_company.
    """
    __tablename__ = "agg_weekly_funnel_company"
    id = Column(Integer, primary_key=True)
    week_start = Column(Date, nullable=False, index=True)
    advertising_company = Column(String(128), nullable=False)
    entered = Column(Integer, nullable=False, default=0)
    new_in_system = Column(Integer, nullable=False, default=0)
    old_in_system = Column(Integer, nullable=False, default=0)
    lead = Column(Integer, nullable=False, default=0)
    subscribed = Column(Integer, nullable=False, default=0)
    platform = Column(Integer, nullable=False, default=0)
    learning = Column(Integer, nullable=False, default=0)
    course = Column(Integer, nullable=False, default=0)
    simulator = Column(Integer, nullable=False, default=0)
    interview = Column(Integer, nullable=False, default=0)
    passed = Column(Integer, nullable=False, default=0)
    offer = Column(Integer, nullable=False, default=0)
    contract = Column(Integer, nullable=False, default=0)
    distance_grinding = Column(Integer, nullable=False, default=0)

    __table_args__ = (
        UniqueConstraint("week_start", "advertising_company", name="uq_weekly_funnel_company"),
        Index("idx_weekly_funnel_company_lookup", "advertising_company", "week_start"),
    )


class BotRegistry(Base):
    """Реестр Telegram-ботов проекта.

    bot_key — уникальный идентификатор (напр. "almanah_ru").
    canonical_base — базовый бот-источник для дедупликации пользователей.
    replicate=True означает, что данные этого бота попадают в PhUserMirrorReplica.
    """
    __tablename__ = "bot_registry"
    bot_key = Column(String(64), primary_key=True)
    display_name = Column(String(128))
    canonical_base = Column(String(128))
    is_active = Column(Boolean, default=True, nullable=False)
    replicate = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class AdvertisingCompany(Base):
    """Рекламные кампании/источники (Roistat-компании).

    utm_rules — JSON-массив правил сопоставления UTM → company_id,
    используется при ингестии для автоматической разметки пользователей.
    """
    __tablename__ = "advertising_companies"
    company_id = Column(String(64), primary_key=True)
    company_name = Column(String(128), nullable=False)
    platform = Column(String(128), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    utm_rules = Column(JSONB, nullable=False, server_default="[]")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class AdvertisingCompanyBot(Base):
    """Связь рекламной компании с ботами (M:M, но бот принадлежит только одной компании).

    UniqueConstraint на bot_key гарантирует, что бот не может быть в двух компаниях.
    """
    __tablename__ = "advertising_company_bots"
    company_id = Column(String(64), ForeignKey("advertising_companies.company_id", ondelete="CASCADE"), primary_key=True)
    bot_key = Column(String(64), primary_key=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (UniqueConstraint("bot_key", name="uq_advertising_company_bot"),)


class TelegramAccess(Base):
    """Белый список Telegram-пользователей, которым разрешён доступ к дашборду.

    Управляется через admin-панель. Дополняется initial_allowed_telegram_ids из config.
    """
    __tablename__ = "telegram_access"
    id = Column(Integer, primary_key=True)
    tg_user_id = Column(BIGINT, nullable=False, unique=True, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    created_by = Column(String(128))


class EmployeeRegistryEntry(Base):
    """Реестр сотрудников (для фильтрации их из воронки).

    Telegram-пользователи из этого списка исключаются из аналитики,
    чтобы не искажать конверсии.
    """
    __tablename__ = "employee_registry"
    id = Column(Integer, primary_key=True)
    tg_user_id = Column(BIGINT, nullable=False, unique=True, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    created_by = Column(String(128))


class TelegramSubscriptionEvent(Base):
    """События подписки/отписки пользователей на Telegram-каналы.

    source — откуда получено событие ("bot_poll" или "mtproto").
    event_at — когда событие произошло, observed_at — когда мы это зафиксировали.
    Используется для построения TgSubsDailyAgg.
    """
    __tablename__ = "telegram_subscription_events"
    id = Column(Integer, primary_key=True)
    tg_user_id = Column(BIGINT, nullable=False, index=True)
    channel_id = Column(String(64), nullable=False)
    status = Column(String(16), nullable=False)
    source = Column(String(32), nullable=False, default="bot_poll")
    event_at = Column(DateTime(timezone=True))
    observed_at = Column(DateTime(timezone=True))
    checked_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        Index("idx_telegram_sub_event_user_channel", "tg_user_id", "channel_id"),
        Index("idx_telegram_sub_event_checked_at", "checked_at"),
    )


class TelegramChatMembership(Base):
    """Актуальное членство пользователей в Telegram-чатах (канал, сообщество).

    Заполняется MTProto-сканером (telegram_membership_service).
    is_member=True — сейчас в чате, False — вышел/кикнут.
    first_seen_member_at / last_seen_member_at отслеживают историю.
    """
    __tablename__ = "telegram_chat_memberships"
    id = Column(Integer, primary_key=True)
    chat_id = Column(String(64), nullable=False, index=True)
    tg_user_id = Column(BIGINT, nullable=False, index=True)
    username = Column(String(128), index=True)
    is_member = Column(Boolean, nullable=False, default=True)
    joined_at = Column(DateTime(timezone=True))
    first_seen_member_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    last_seen_member_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    last_status_change_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    source = Column(String(32), nullable=False, default="full_sync")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("chat_id", "tg_user_id", name="uq_telegram_chat_membership"),
        Index("idx_telegram_chat_membership_chat_member", "chat_id", "is_member"),
        Index("idx_telegram_chat_membership_last_seen", "chat_id", "last_seen_member_at"),
    )


class TelegramChatTotal(Base):
    """Общее число участников чата по данным Telegram API.

    Обновляется при каждом полном сканировании.
    Используется как верхняя цифра в отчёте по подпискам.
    """
    __tablename__ = "telegram_chat_totals"
    id = Column(Integer, primary_key=True)
    chat_id = Column(String(64), nullable=False, unique=True, index=True)
    participants_count = Column(Integer, nullable=False, default=0)
    source = Column(String(32), nullable=False, default="full_sync")
    observed_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("idx_telegram_chat_total_observed_at", "observed_at"),
    )


class SystemSetting(Base):
    """Произвольные системные настройки в формате key → JSON.

    Используется для хранения конфигурации, которую нужно менять без деплоя
    (напр. расписание Marketing Daily, включение фич).
    """
    __tablename__ = "system_settings"
    key = Column(String(64), primary_key=True)
    value = Column(JSONB, nullable=False, default=dict)
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class SyncEventLog(Base):
    """Лог событий синхронизации (ингестия, Google Sheets, PokerHub и др.).

    level — "info" / "warning" / "error". Показывается в admin-панели.
    """
    __tablename__ = "sync_event_logs"
    id = Column(Integer, primary_key=True)
    source = Column(String(64), nullable=False)
    level = Column(String(16), nullable=False)
    message = Column(String(1024), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (Index("idx_sync_event_logs_created_at", "created_at"),)


class ReplicationDLQ(Base):
    """Dead Letter Queue для репликации из внешних БД.

    Записи попадают сюда, если replication_worker не смог применить
    событие после нескольких попыток. reason — тип ошибки, payload — исходный JSON,
    error — текст исключения. Позволяет вручную разобрать застрявшие события.
    """
    __tablename__ = "replication_dlq"
    id = Column(BIGINT, primary_key=True)
    db_name = Column(String(128), nullable=False, index=True)
    bot_key = Column(String(128), nullable=False, index=True)
    reason = Column(String(128), nullable=False, index=True)
    payload = Column(Text)
    error = Column(Text)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        Index("idx_replication_dlq_created_at", "created_at"),
    )


class BudgetWeekly(Base):
    """Рекламный бюджет по неделям и кампаниям.

    Вводится вручную через admin-панель или импортируется из Google Sheets.
    period_end позволяет задать нестандартный конец периода (не всегда воскресенье).
    channel_key — разбивка внутри кампании по каналу (напр. telegram, vk).
    """
    __tablename__ = "budget_weekly"
    id = Column(Integer, primary_key=True)
    week_start = Column(Date, nullable=False, index=True)
    period_end = Column(Date, nullable=True)
    campaign = Column(String(128), nullable=False, index=True)
    bot_key = Column(String(64))
    channel_key = Column(String(32), nullable=True, index=True)
    utm_source = Column(String(128), nullable=True, index=True)
    utm_campaign = Column(String(128), nullable=True, index=True)
    utm_medium = Column(String(128), nullable=True, index=True)
    utm_content = Column(String(256), nullable=True)
    utm_term = Column(String(256), nullable=True)
    amount = Column(Float, nullable=False, default=0.0)
    currency = Column(String(8), nullable=False, default="USD")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("idx_budget_weekly_campaign_week", "campaign", "week_start"),
        Index(
            "idx_budget_weekly_utm_combo",
            "week_start",
            "utm_source",
            "utm_campaign",
            "utm_medium",
        ),
    )


class AdMetricsWeekly(Base):
    """Рекламные метрики по неделям: показы, клики, расходы.

    Импортируется из Google Sheets или вводится вручную.
    Используется в Roistat-отчётах для расчёта CPM/CPC.
    """
    __tablename__ = "ad_metrics_weekly"
    id = Column(Integer, primary_key=True)
    week_start = Column(Date, nullable=False, index=True)
    campaign = Column(String(128), nullable=False, index=True)
    bot_key = Column(String(64))
    impressions = Column(Integer, nullable=False, default=0)
    clicks = Column(Integer, nullable=False, default=0)
    spend = Column(Float, nullable=False, default=0.0)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("idx_ad_metrics_weekly_campaign_week", "campaign", "week_start"),
    )
