from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class TelegramMembershipRealtimeMonitor:
    """
    Realtime listener skeleton.

    Intentionally not wired into worker startup yet. Full sync is the primary
    reliable source; realtime will be attached after the MTProto session and
    production event handling are validated.
    """

    def __init__(self) -> None:
        self._logger = logging.getLogger("telegram_membership_realtime")

    async def run(self) -> None:
        """Запускает realtime-мониторинг участников чата через MTProto.

        Два механизма работают параллельно:
        1. _poll_admin_log_loop — опрашивает AdminLog каждые 15 сек (cursor-based, не пропускает события).
           Каждые 20 итераций (~5 мин) сверяет реальный счётчик с Telegram API.
        2. ChatAction-хендлер — получает события join/leave в реальном времени через Telethon.
        3. Raw Update-хендлер — обрабатывает UpdateChannelParticipant напрямую.

        Курсор AdminLog сохраняется в Redis (ключ telegram:membership:adminlog:last_event:{chat_id})
        чтобы не терять события при перезапуске.
        """
        from telethon import events
        from telethon.tl import types
        from app.services.telegram_membership_parts.telegram_membership_service import TelegramMembershipService

        service = TelegramMembershipService()
        service.ensure_configured()
        chat_ids = {int(chat_id) for chat_id in service.configured_chat_ids()}
        admin_log_join_actions = (
            types.ChannelAdminLogEventActionParticipantJoin,
            types.ChannelAdminLogEventActionParticipantJoinByInvite,
            types.ChannelAdminLogEventActionParticipantJoinByRequest,
            types.ChannelAdminLogEventActionParticipantInvite,
        )
        admin_log_leave_actions = (
            types.ChannelAdminLogEventActionParticipantLeave,
        )

        def _participant_is_member(participant) -> bool:
            if participant is None:
                return False
            return not isinstance(
                participant,
                (
                    types.ChannelParticipantLeft,
                    types.ChannelParticipantBanned,
                ),
            )

        def _extract_update_chat_id(update) -> int | None:
            for attr in ("channel_id", "chat_id"):
                value = getattr(update, attr, None)
                if isinstance(value, int):
                    return value

            message = getattr(update, "message", None)
            peer = getattr(message, "peer_id", None)
            channel_id = getattr(peer, "channel_id", None)
            if isinstance(channel_id, int):
                return channel_id
            return None

        async def _invalidate_and_refresh_reports() -> None:
            from app.core.redis_client import RedisCache

            cache = RedisCache()
            await cache.delete_pattern("reports:subscriptions_vs_starts:*")
            await cache.delete("reports:stages")
            await cache.set("replication:needs_refresh", "1", ttl=300)

        async def _get_admin_log_cursor(chat_id: int) -> int | None:
            from app.core.redis_client import RedisCache

            cache = RedisCache()
            value = await cache.get_json(f"telegram:membership:adminlog:last_event:{chat_id}")
            if value is None:
                return None
            try:
                return int(value)
            except (TypeError, ValueError):
                return None

        async def _set_admin_log_cursor(chat_id: int, event_id: int) -> None:
            from app.core.redis_client import RedisCache

            cache = RedisCache()
            await cache.set_json(f"telegram:membership:adminlog:last_event:{chat_id}", int(event_id), ttl=30 * 24 * 60 * 60)

        async def _apply_single_membership_change(
            *,
            chat_id: int,
            tg_user_id: int,
            is_member: bool,
            event_time: datetime,
            username: str | None = None,
            joined_at: datetime | None = None,
            source: str = "realtime",
        ) -> None:
            from app.db.session import async_session

            async with async_session() as session:
                await service.apply_realtime_membership_event(
                    session=session,
                    chat_id=str(chat_id),
                    tg_user_id=int(tg_user_id),
                    is_member=bool(is_member),
                    username=username,
                    joined_at=joined_at,
                    source=source,
                    event_at=event_time,
                )
                await service.reconcile_raw_user_flags(session)
                await session.commit()
            await _invalidate_and_refresh_reports()

        async def _bootstrap_admin_log_cursor(chat_id: int) -> int:
            cursor = await _get_admin_log_cursor(chat_id)
            if cursor is not None:
                return cursor

            latest_event_id = 0
            async for event in client.iter_admin_log(
                chat_id,
                limit=1,
                join=True,
                leave=True,
                invite=True,
            ):
                latest_event_id = int(getattr(event, "id", 0) or 0)
                break
            await _set_admin_log_cursor(chat_id, latest_event_id)
            self._logger.info(
                "Admin log cursor initialized chat_id=%s last_event_id=%s",
                chat_id,
                latest_event_id,
            )
            return latest_event_id

        async def _reconcile_chat_count(chat_id: int) -> None:
            from telethon.tl.functions.channels import GetFullChannelRequest

            try:
                entity = await client.get_entity(chat_id)
                full = await client(GetFullChannelRequest(entity))
                real_count = getattr(getattr(full, "full_chat", None), "participants_count", None)
                if real_count is not None:
                    self._logger.info(
                        "Count reconcile chat_id=%s real_count=%s",
                        chat_id,
                        real_count,
                    )
                    from app.db.session import async_session

                    async with async_session() as session:
                        await service.upsert_chat_total(
                            session=session,
                            chat_id=str(chat_id),
                            participants_count=int(real_count),
                            source="realtime_reconcile",
                            observed_at=datetime.now(timezone.utc),
                        )
                        await session.commit()
                    await _invalidate_and_refresh_reports()
            except Exception as exc:
                self._logger.warning("Count reconcile failed chat_id=%s error=%s", chat_id, exc)

        async def _poll_admin_log_loop() -> None:
            cursors = {
                chat_id: await _bootstrap_admin_log_cursor(chat_id)
                for chat_id in sorted(chat_ids)
            }
            poll_counts: dict[int, int] = {chat_id: 0 for chat_id in chat_ids}
            RECONCILE_EVERY = 20  # каждые 20 × 15с = 5 минут
            while True:
                for chat_id in sorted(chat_ids):
                    cursor = cursors.get(chat_id, 0)
                    fresh_events = []
                    async for event in client.iter_admin_log(
                        chat_id,
                        min_id=cursor,
                        limit=100,
                        join=True,
                        leave=True,
                        invite=True,
                    ):
                        event_id = int(getattr(event, "id", 0) or 0)
                        if event_id <= cursor:
                            continue
                        fresh_events.append(event)

                    if not fresh_events:
                        continue

                    fresh_events.sort(key=lambda item: int(getattr(item, "id", 0) or 0))
                    for event in fresh_events:
                        action = getattr(event, "action", None)
                        event_id = int(getattr(event, "id", 0) or 0)
                        event_time = getattr(event, "date", None) or datetime.now(timezone.utc)
                        user = getattr(event, "user", None)
                        tg_user_id = getattr(user, "id", None)
                        if tg_user_id is None:
                            self._logger.info(
                                "Admin log event skipped chat_id=%s event_id=%s action=%s no-user",
                                chat_id,
                                event_id,
                                type(action).__name__,
                            )
                            cursors[chat_id] = max(cursors.get(chat_id, 0), event_id)
                            await _set_admin_log_cursor(chat_id, cursors[chat_id])
                            continue

                        if isinstance(action, admin_log_join_actions):
                            is_member = True
                        elif isinstance(action, admin_log_leave_actions):
                            is_member = False
                        else:
                            self._logger.info(
                                "Admin log event ignored chat_id=%s event_id=%s action=%s",
                                chat_id,
                                event_id,
                                type(action).__name__,
                            )
                            cursors[chat_id] = max(cursors.get(chat_id, 0), event_id)
                            await _set_admin_log_cursor(chat_id, cursors[chat_id])
                            continue

                        self._logger.info(
                            "Admin log membership change chat_id=%s event_id=%s user_id=%s is_member=%s action=%s",
                            chat_id,
                            event_id,
                            tg_user_id,
                            is_member,
                            type(action).__name__,
                        )
                        await _apply_single_membership_change(
                            chat_id=chat_id,
                            tg_user_id=int(tg_user_id),
                            is_member=is_member,
                            username=getattr(user, "username", None),
                            joined_at=event_time if is_member else None,
                            event_time=event_time,
                            source="realtime_admin_log",
                        )
                        cursors[chat_id] = max(cursors.get(chat_id, 0), event_id)
                        await _set_admin_log_cursor(chat_id, cursors[chat_id])

                await asyncio.sleep(15)

                for chat_id in sorted(chat_ids):
                    poll_counts[chat_id] = poll_counts.get(chat_id, 0) + 1
                    if poll_counts[chat_id] >= RECONCILE_EVERY:
                        poll_counts[chat_id] = 0
                        await _reconcile_chat_count(chat_id)

        async with service.mtproto_client() as client:
            self._logger.info("Telegram realtime monitor starting for chats=%s", sorted(chat_ids))
            admin_log_task = asyncio.create_task(_poll_admin_log_loop())

            @client.on(events.ChatAction(chats=list(chat_ids)))
            async def _handle_chat_action(event):
                chat_id = getattr(event, "chat_id", None)
                if chat_id is None:
                    return
                event_time = getattr(event, "date", None) or datetime.now(timezone.utc)

                joined_users = []
                if getattr(event, "user_joined", False) or getattr(event, "user_added", False):
                    joined_users = list(getattr(event, "users", None) or [])
                left_users = []
                if getattr(event, "user_left", False) or getattr(event, "user_kicked", False):
                    left_users = list(getattr(event, "users", None) or [])

                if not joined_users and not left_users:
                    self._logger.info(
                        "ChatAction ignored for chat_id=%s action_flags={joined=%s added=%s left=%s kicked=%s}",
                        chat_id,
                        getattr(event, "user_joined", False),
                        getattr(event, "user_added", False),
                        getattr(event, "user_left", False),
                        getattr(event, "user_kicked", False),
                    )
                    return

                self._logger.info(
                    "ChatAction membership update chat_id=%s joined=%s left=%s",
                    chat_id,
                    [int(user.id) for user in joined_users],
                    [int(user.id) for user in left_users],
                )
                for user in joined_users:
                    await _apply_single_membership_change(
                        chat_id=int(chat_id),
                        tg_user_id=int(user.id),
                        is_member=True,
                        username=getattr(user, "username", None),
                        joined_at=getattr(user, "date", None) or event_time,
                        event_time=event_time,
                    )
                for user in left_users:
                    await _apply_single_membership_change(
                        chat_id=int(chat_id),
                        tg_user_id=int(user.id),
                        is_member=False,
                        username=getattr(user, "username", None),
                        event_time=event_time,
                    )

            @client.on(events.Raw)
            async def _handle_raw_update(update):
                update_chat_id = _extract_update_chat_id(update)
                if update_chat_id not in {abs(chat_id) for chat_id in chat_ids} and update_chat_id not in chat_ids:
                    return

                self._logger.info(
                    "Raw update for tracked chat: type=%s chat_id=%s",
                    type(update).__name__,
                    update_chat_id,
                )

                if not isinstance(update, types.UpdateChannelParticipant):
                    return

                actual_chat_id = -1000000000000 - int(update.channel_id)
                if actual_chat_id not in chat_ids:
                    actual_chat_id = int(update.channel_id)
                prev_is_member = _participant_is_member(update.prev_participant)
                new_is_member = _participant_is_member(update.new_participant)
                if prev_is_member == new_is_member:
                    self._logger.info(
                        "UpdateChannelParticipant no membership change chat_id=%s user_id=%s prev=%s new=%s",
                        actual_chat_id,
                        update.user_id,
                        type(update.prev_participant).__name__ if update.prev_participant else None,
                        type(update.new_participant).__name__ if update.new_participant else None,
                    )
                    return

                event_time = update.date or datetime.now(timezone.utc)
                self._logger.info(
                    "UpdateChannelParticipant membership change chat_id=%s user_id=%s %s->%s",
                    actual_chat_id,
                    update.user_id,
                    prev_is_member,
                    new_is_member,
                )
                await _apply_single_membership_change(
                    chat_id=actual_chat_id,
                    tg_user_id=int(update.user_id),
                    is_member=new_is_member,
                    joined_at=event_time if new_is_member else None,
                    event_time=event_time,
                    source="realtime_raw",
                )

            try:
                await client.run_until_disconnected()
            finally:
                admin_log_task.cancel()
                try:
                    await admin_log_task
                except asyncio.CancelledError:
                    pass
