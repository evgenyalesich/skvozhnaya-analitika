from app.services.telegram_membership_parts.telegram_membership_core import (
    ChatMembersSnapshot,
    MembershipSyncStats,
    TelegramMembershipCoreMixin,
)
from app.services.telegram_membership_parts.telegram_membership_realtime import TelegramMembershipRealtimeMonitor
from app.services.telegram_membership_parts.telegram_membership_sync import TelegramMembershipSyncMixin


class TelegramMembershipService(TelegramMembershipCoreMixin, TelegramMembershipSyncMixin):
    """Сервис синхронизации членства в Telegram-чатах (канал + сообщество).

    Слои:
    - Core — MTProto-клиент (Telethon), полное сканирование (fetch_chat_members),
             счётчики участников (upsert/adjust_chat_total)
    - Sync — bulk-синхронизация snapshot с БД (sync_chat_memberships),
             realtime-событие (apply_realtime_membership_event),
             актуализация флагов в raw_bot_users (reconcile_raw_user_flags)

    Realtime-мониторинг — отдельный класс TelegramMembershipRealtimeMonitor.
    """


__all__ = [
    "MembershipSyncStats",
    "ChatMembersSnapshot",
    "TelegramMembershipService",
    "TelegramMembershipRealtimeMonitor",
]
