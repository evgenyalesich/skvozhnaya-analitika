from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import and_, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analytics import RawBotUser, TelegramChatMembership, TelegramSubscriptionEvent


class TelegramMembershipSyncMixin:
    """Синхронизация снимка участников чата с базой данных.

    Отвечает за:
    - применение realtime-события (один пользователь вошёл/вышел)
    - полную синхронизацию снимка (bulk upsert + пометка ушедших)
    - обновление флагов channel_subscribed/community_member в raw_bot_users
    """

    async def _resolve_joined_dates(self, client, chat_id: str, user_ids: list[int]) -> dict[int, Optional[datetime]]:
        """Параллельно запрашивает joined_at для конкретных пользователей через GetParticipantRequest.

        Ограничивает параллелизм через Semaphore (telegram_membership_joined_at_concurrency).
        """
        try:
            from telethon.tl.functions.channels import GetParticipantRequest
        except ImportError as exc:
            raise RuntimeError("Telethon is not installed. Run pip install -r backend/requirements.txt") from exc

        semaphore = asyncio.Semaphore(max(1, settings.telegram_membership_joined_at_concurrency))
        resolved: dict[int, Optional[datetime]] = {}

        async def _fetch(user_id: int) -> None:
            async with semaphore:
                try:
                    participant = await client(GetParticipantRequest(channel=int(chat_id), participant=user_id))
                    resolved[user_id] = getattr(getattr(participant, "participant", None), "date", None)
                except Exception:
                    resolved[user_id] = None

        await asyncio.gather(*(_fetch(user_id) for user_id in user_ids))
        return resolved

    async def apply_realtime_membership_event(
        self,
        session: AsyncSession,
        chat_id: str,
        tg_user_id: int,
        is_member: bool,
        username: Optional[str] = None,
        joined_at: Optional[datetime] = None,
        source: str = "realtime",
        event_at: Optional[datetime] = None,
    ) -> None:
        """Применяет одно realtime-событие (join/leave) к TelegramChatMembership.

        Если запись не существует - создаёт новую + пишет TelegramSubscriptionEvent.
        Если существует и статус изменился - обновляет + пишет событие.
        Обновляет счётчик участников через adjust_chat_total (+/-1).
        """
        event_at = event_at or datetime.now(timezone.utc)
        total_delta = 0
        existing = (
            await session.execute(
                select(TelegramChatMembership).where(
                    TelegramChatMembership.chat_id == str(chat_id),
                    TelegramChatMembership.tg_user_id == int(tg_user_id),
                )
            )
        ).scalar_one_or_none()

        if existing is None:
            stmt = insert(TelegramChatMembership).values(
                {
                    "chat_id": str(chat_id),
                    "tg_user_id": int(tg_user_id),
                    "username": username,
                    "is_member": bool(is_member),
                    "joined_at": joined_at or event_at,
                    "first_seen_member_at": event_at,
                    "last_seen_member_at": event_at,
                    "last_status_change_at": event_at,
                    "source": source,
                }
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["chat_id", "tg_user_id"],
                set_={
                    "username": stmt.excluded.username,
                    "is_member": stmt.excluded.is_member,
                    "joined_at": func.coalesce(TelegramChatMembership.joined_at, stmt.excluded.joined_at),
                    "last_seen_member_at": stmt.excluded.last_seen_member_at,
                    "last_status_change_at": stmt.excluded.last_status_change_at,
                    "source": stmt.excluded.source,
                    "updated_at": event_at,
                },
            )
            await session.execute(stmt)
            session.add(
                TelegramSubscriptionEvent(
                    tg_user_id=int(tg_user_id),
                    channel_id=str(chat_id),
                    status="subscribed" if is_member else "unsubscribed",
                    source=source,
                    event_at=event_at,
                    observed_at=event_at,
                )
            )
            total_delta = 1 if is_member else -1
            await self.adjust_chat_total(session, chat_id, total_delta, source, event_at)
            return

        prev_member = bool(existing.is_member)
        updates = {
            "username": username or existing.username,
            "joined_at": existing.joined_at or joined_at,
            "last_seen_member_at": event_at,
            "source": source,
            "updated_at": event_at,
        }
        if prev_member != bool(is_member):
            updates["is_member"] = bool(is_member)
            updates["last_status_change_at"] = event_at
            session.add(
                TelegramSubscriptionEvent(
                    tg_user_id=int(tg_user_id),
                    channel_id=str(chat_id),
                    status="subscribed" if is_member else "unsubscribed",
                    source=source,
                    event_at=event_at,
                    observed_at=event_at,
                )
            )
            total_delta = 1 if is_member else -1
        elif is_member:
            updates["is_member"] = True

        await session.execute(
            update(TelegramChatMembership)
            .where(
                TelegramChatMembership.chat_id == str(chat_id),
                TelegramChatMembership.tg_user_id == int(tg_user_id),
            )
            .values(**updates)
        )
        await self.adjust_chat_total(session, chat_id, total_delta, source, event_at)

    async def sync_chat_memberships(
        # Bulk-синхронизация после полного сканирования чата.
        # Upsert всех участников из snapshot, пометка departed (is_member=False)
        # для тех, кого нет в snapshot, запись событий subscribed/unsubscribed.
        self,
        session: AsyncSession,
        chat_id: str,
        members: Iterable[dict[str, Optional[str]]],
        source: str = "full_sync",
        observed_at: Optional[datetime] = None,
    ) -> MembershipSyncStats:
        observed_at = observed_at or datetime.now(timezone.utc)
        rows = list(members)
        stats = MembershipSyncStats(chat_id=chat_id, seen_members=len(rows))
        member_ids = {int(row["tg_user_id"]) for row in rows if row.get("tg_user_id") is not None}

        existing_rows = (
            await session.execute(
                select(TelegramChatMembership).where(TelegramChatMembership.chat_id == str(chat_id))
            )
        ).scalars().all()
        existing_map = {int(row.tg_user_id): row for row in existing_rows}

        upserts: list[dict[str, object]] = []
        events: list[TelegramSubscriptionEvent] = []

        for row in rows:
            tg_user_id = int(row["tg_user_id"])
            username = row.get("username")
            joined_at = row.get("joined_at")
            existing = existing_map.get(tg_user_id)
            was_member = bool(existing.is_member) if existing else False
            if existing is None:
                stats.inserted += 1
                stats.activated += 1
            else:
                stats.updated += 1
                if not was_member:
                    stats.activated += 1
            upserts.append(
                {
                    "chat_id": str(chat_id),
                    "tg_user_id": tg_user_id,
                    "username": username,
                    "is_member": True,
                    "joined_at": existing.joined_at if existing and existing.joined_at else joined_at,
                    "first_seen_member_at": existing.first_seen_member_at if existing else observed_at,
                    "last_seen_member_at": observed_at,
                    "last_status_change_at": observed_at if not was_member else existing.last_status_change_at,
                    "source": source,
                }
            )
            if not was_member:
                events.append(
                    TelegramSubscriptionEvent(
                        tg_user_id=tg_user_id,
                        channel_id=str(chat_id),
                        status="subscribed",
                        source=source,
                        event_at=observed_at,
                        observed_at=observed_at,
                    )
                )

        if upserts:
            stmt = insert(TelegramChatMembership).values(upserts)
            stmt = stmt.on_conflict_do_update(
                index_elements=["chat_id", "tg_user_id"],
                set_={
                    "username": stmt.excluded.username,
                    "is_member": True,
                    "joined_at": func.coalesce(TelegramChatMembership.joined_at, stmt.excluded.joined_at),
                    "last_seen_member_at": stmt.excluded.last_seen_member_at,
                    "last_status_change_at": case(
                        (
                            TelegramChatMembership.is_member.is_(False),
                            stmt.excluded.last_status_change_at,
                        ),
                        else_=TelegramChatMembership.last_status_change_at,
                    ),
                    "source": stmt.excluded.source,
                    "updated_at": observed_at,
                },
            )
            await session.execute(stmt)

        departed_ids = [
            tg_user_id
            for tg_user_id, existing in existing_map.items()
            if existing.is_member and tg_user_id not in member_ids
        ]
        if departed_ids:
            stats.deactivated = len(departed_ids)
            await session.execute(
                update(TelegramChatMembership)
                .where(
                    and_(
                        TelegramChatMembership.chat_id == str(chat_id),
                        TelegramChatMembership.tg_user_id.in_(departed_ids),
                        TelegramChatMembership.is_member.is_(True),
                    )
                )
                .values(
                    is_member=False,
                    last_status_change_at=observed_at,
                    source=source,
                    updated_at=observed_at,
                )
            )
            events.extend(
                TelegramSubscriptionEvent(
                    tg_user_id=tg_user_id,
                    channel_id=str(chat_id),
                    status="unsubscribed",
                    source=source,
                    event_at=observed_at,
                    observed_at=observed_at,
                )
                for tg_user_id in departed_ids
            )

        if events:
            session.add_all(events)
        return stats

    async def reconcile_raw_user_flags(
        # Синхронизирует channel_subscribed / community_member в raw_bot_users
        # из актуальных данных telegram_chat_memberships (подзапрос-скалярный SELECT).
        # Вызывается после каждой синхронизации чтобы raw-данные были актуальны.
        self,
        session: AsyncSession,
        channel_id: Optional[str] = None,
        community_id: Optional[str] = None,
    ) -> None:
        channel_id = channel_id or os.getenv("TELEGRAM_CHANNEL_ID")
        community_id = community_id or os.getenv("TELEGRAM_COMMUNITY_ID")

        values: dict[str, object] = {}
        if channel_id:
            values["channel_subscribed"] = func.coalesce(
                (
                    select(TelegramChatMembership.is_member)
                    .where(
                        TelegramChatMembership.chat_id == str(channel_id),
                        TelegramChatMembership.tg_user_id == RawBotUser.tg_user_id,
                    )
                    .limit(1)
                    .scalar_subquery()
                ),
                False,
            )
            values["channel_subscribed_at"] = func.coalesce(
                RawBotUser.channel_subscribed_at,
                (
                    select(func.min(TelegramChatMembership.joined_at))
                    .where(
                        TelegramChatMembership.chat_id == str(channel_id),
                        TelegramChatMembership.tg_user_id == RawBotUser.tg_user_id,
                        TelegramChatMembership.joined_at.is_not(None),
                    )
                    .scalar_subquery()
                ),
            )
        if community_id:
            values["community_member"] = func.coalesce(
                (
                    select(TelegramChatMembership.is_member)
                    .where(
                        TelegramChatMembership.chat_id == str(community_id),
                        TelegramChatMembership.tg_user_id == RawBotUser.tg_user_id,
                    )
                    .limit(1)
                    .scalar_subquery()
                ),
                False,
            )
        if not values:
            return
        await session.execute(update(RawBotUser).values(**values))

    async def run_full_sync(
        # Главная точка входа для полного сканирования: открывает MTProto-клиент,
        # для каждого чата вызывает fetch_chat_members → upsert_chat_total → sync_chat_memberships,
        # затем reconcile_raw_user_flags.
        self,
        session: AsyncSession,
        chat_ids: Optional[list[str]] = None,
        source: str = "full_sync",
    ) -> list[MembershipSyncStats]:
        self.ensure_configured()
        chat_ids = chat_ids or self.configured_chat_ids()
        observed_at = datetime.now(timezone.utc)
        results: list[MembershipSyncStats] = []
        async with self.mtproto_client() as client:
            for chat_id in chat_ids:
                self._logger.info("Telegram membership full sync: loading chat_id=%s", chat_id)
                snapshot = await self.fetch_chat_members(client, chat_id)
                await self.upsert_chat_total(
                    session=session,
                    chat_id=chat_id,
                    participants_count=snapshot.participants_count,
                    source=source,
                    observed_at=observed_at,
                )
                stats = await self.sync_chat_memberships(
                    session=session,
                    chat_id=chat_id,
                    members=snapshot.members,
                    source=source,
                    observed_at=observed_at,
                )
                stats.participants_count = snapshot.participants_count
                results.append(stats)
        await self.reconcile_raw_user_flags(session)
        return results
