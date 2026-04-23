from __future__ import annotations

import logging
import os
import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

from sqlalchemy import and_, case, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.analytics import RawBotUser, TelegramChatMembership, TelegramChatTotal, TelegramSubscriptionEvent

ROOT_DIR = Path(__file__).resolve().parents[3]


@dataclass(slots=True)
class MembershipSyncStats:
    chat_id: str
    seen_members: int = 0
    participants_count: int = 0
    activated: int = 0
    deactivated: int = 0
    inserted: int = 0
    updated: int = 0


@dataclass(slots=True)
class ChatMembersSnapshot:
    chat_id: str
    members: list[dict[str, Optional[str]]]
    participants_count: int = 0


class TelegramMembershipService:
    def __init__(self) -> None:
        self._logger = logging.getLogger("telegram_membership_service")

    def configured_chat_ids(self) -> list[str]:
        configured = list(settings.telegram_membership_chat_ids)
        for env_name in ("TELEGRAM_CHANNEL_ID", "TELEGRAM_COMMUNITY_ID"):
            value = os.getenv(env_name)
            if value and value not in configured:
                configured.append(value)
        return configured

    def ensure_configured(self) -> None:
        if not settings.telegram_api_id or not settings.telegram_api_hash:
            raise RuntimeError("TELEGRAM_API_ID/TELEGRAM_API_HASH are not configured")
        if not self.configured_chat_ids():
            raise RuntimeError("No Telegram membership chat ids configured")

    @asynccontextmanager
    async def mtproto_client(self):
        try:
            from telethon import TelegramClient
        except ImportError as exc:
            raise RuntimeError("Telethon is not installed. Run pip install -r backend/requirements.txt") from exc

        session_name = str(ROOT_DIR / settings.telegram_mtproto_session_name)
        client = TelegramClient(session_name, settings.telegram_api_id, settings.telegram_api_hash)
        await client.connect()
        try:
            if not await client.is_user_authorized():
                raise RuntimeError(
                    "MTProto session is not authorized. Run an interactive login once before starting sync."
                )
            yield client
        finally:
            await client.disconnect()

    async def fetch_chat_members(self, client, chat_id: str) -> ChatMembersSnapshot:
        try:
            from telethon.errors import FloodWaitError
            from telethon.tl.functions.channels import GetFullChannelRequest, GetParticipantsRequest
            from telethon.tl.types import ChannelParticipantsRecent, ChannelParticipantsSearch
        except ImportError as exc:
            raise RuntimeError("Telethon is not installed. Run pip install -r backend/requirements.txt") from exc

        import string

        entity = await client.get_entity(int(chat_id))
        expected_count: Optional[int] = None
        try:
            full = await client(GetFullChannelRequest(entity))
            expected_count = getattr(getattr(full, "full_chat", None), "participants_count", None)
        except Exception as exc:
            self._logger.warning(
                "Telegram membership full sync: unable to load full chat count chat_id=%s error=%s", chat_id, exc
            )

        members_dict: dict[int, dict[str, object]] = {}
        limit = 200

        # ── Stage 1: ChannelParticipantsRecent ──────────────────────────────────
        self._logger.info(
            "Telegram membership full sync [stage 1/2 Recent]: chat_id=%s expected=%s",
            chat_id,
            expected_count,
        )
        offset = 0
        while True:
            try:
                page = await client(
                    GetParticipantsRequest(
                        channel=entity,
                        filter=ChannelParticipantsRecent(),
                        offset=offset,
                        limit=limit,
                        hash=0,
                    )
                )
            except FloodWaitError as exc:
                self._logger.warning("FloodWait stage1 chat_id=%s wait=%ss", chat_id, exc.seconds)
                await asyncio.sleep(exc.seconds + 1)
                continue

            users = list(getattr(page, "users", None) or [])
            participants = list(getattr(page, "participants", None) or [])
            if not users:
                break

            joined_at_map: dict[int, Optional[datetime]] = {}
            for p in participants:
                uid = getattr(p, "user_id", None)
                if uid is not None:
                    joined_at_map[int(uid)] = getattr(p, "date", None)

            added = 0
            for user in users:
                if not getattr(user, "id", None):
                    continue
                tg_user_id = int(user.id)
                if tg_user_id not in members_dict:
                    members_dict[tg_user_id] = {
                        "tg_user_id": tg_user_id,
                        "username": getattr(user, "username", None),
                        "joined_at": joined_at_map.get(tg_user_id),
                    }
                    added += 1

            self._logger.info(
                "Telegram membership [stage1] chat_id=%s offset=%s page=%s added=%s total=%s expected=%s",
                chat_id,
                offset,
                len(users),
                added,
                len(members_dict),
                expected_count,
            )
            offset += limit
            if len(users) < limit:
                break
            await asyncio.sleep(0.3)

        # ── Stage 2: letter-by-letter search if we didn't collect everyone ──────
        if expected_count is None or len(members_dict) < expected_count:
            missing = (expected_count or 0) - len(members_dict)
            self._logger.info(
                "Telegram membership full sync [stage 2/2 Search]: chat_id=%s collected=%s expected=%s missing=%s",
                chat_id,
                len(members_dict),
                expected_count,
                missing,
            )
            search_chars = (
                list(string.ascii_lowercase)
                + list("абвгдеёжзийклмнопрстуфхцчшщъыьэюя")
                + list(string.digits)
                + list("_-.+!@#$%&*")
            )
            for idx, char in enumerate(search_chars):
                added = 0
                offset = 0
                while True:
                    try:
                        page = await client(
                            GetParticipantsRequest(
                                channel=entity,
                                filter=ChannelParticipantsSearch(q=char),
                                offset=offset,
                                limit=limit,
                                hash=0,
                            )
                        )
                    except FloodWaitError as exc:
                        self._logger.warning("FloodWait stage2 char=%r chat_id=%s wait=%ss", char, chat_id, exc.seconds)
                        await asyncio.sleep(exc.seconds + 1)
                        continue

                    users = list(getattr(page, "users", None) or [])
                    if not users:
                        break

                    participants = list(getattr(page, "participants", None) or [])
                    joined_at_map = {}
                    for p in participants:
                        uid = getattr(p, "user_id", None)
                        if uid is not None:
                            joined_at_map[int(uid)] = getattr(p, "date", None)

                    for user in users:
                        if not getattr(user, "id", None):
                            continue
                        tg_user_id = int(user.id)
                        if tg_user_id not in members_dict:
                            members_dict[tg_user_id] = {
                                "tg_user_id": tg_user_id,
                                "username": getattr(user, "username", None),
                                "joined_at": joined_at_map.get(tg_user_id),
                            }
                            added += 1

                    offset += limit
                    if len(users) < limit:
                        break
                    await asyncio.sleep(0.3)

                if added > 0 or (idx % 10 == 0):
                    self._logger.info(
                        "Telegram membership [stage2] chat_id=%s char=%r step=%s/%s total=%s expected=%s",
                        chat_id,
                        char,
                        idx + 1,
                        len(search_chars),
                        len(members_dict),
                        expected_count,
                    )
        else:
            self._logger.info(
                "Telegram membership full sync: chat_id=%s stage 2 skipped (collected %s >= expected %s)",
                chat_id,
                len(members_dict),
                expected_count,
            )

        members = list(members_dict.values())

        # ── Resolve missing joined_at dates ─────────────────────────────────────
        if settings.telegram_membership_resolve_joined_at and members:
            missing_joined_ids = [
                int(row["tg_user_id"])
                for row in members
                if not row.get("joined_at")
            ]
            if missing_joined_ids:
                joined_at_resolved = await self._resolve_joined_dates(client, chat_id, missing_joined_ids)
                for row in members:
                    if row.get("joined_at"):
                        continue
                    resolved = joined_at_resolved.get(int(row["tg_user_id"]))
                    if resolved:
                        row["joined_at"] = resolved

        self._logger.info(
            "Telegram membership full sync: chat_id=%s fetched_members=%s expected_members=%s joined_at_filled=%s",
            chat_id,
            len(members),
            expected_count,
            sum(1 for row in members if row.get("joined_at")),
        )
        return ChatMembersSnapshot(
            chat_id=str(chat_id),
            members=members,
            participants_count=int(expected_count or len(members)),
        )

    async def upsert_chat_total(
        self,
        session: AsyncSession,
        chat_id: str,
        participants_count: int,
        source: str,
        observed_at: datetime,
    ) -> None:
        stmt = insert(TelegramChatTotal).values(
            {
                "chat_id": str(chat_id),
                "participants_count": int(participants_count),
                "source": source,
                "observed_at": observed_at,
            }
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["chat_id"],
            set_={
                "participants_count": stmt.excluded.participants_count,
                "source": stmt.excluded.source,
                "observed_at": stmt.excluded.observed_at,
                "updated_at": observed_at,
            },
        )
        await session.execute(stmt)

    async def adjust_chat_total(
        self,
        session: AsyncSession,
        chat_id: str,
        delta: int,
        source: str,
        observed_at: datetime,
    ) -> None:
        if delta == 0:
            return
        current_total = (
            await session.execute(
                select(TelegramChatTotal).where(TelegramChatTotal.chat_id == str(chat_id))
            )
        ).scalar_one_or_none()
        next_count = max(int((current_total.participants_count if current_total else 0) or 0) + int(delta), 0)
        await self.upsert_chat_total(
            session=session,
            chat_id=chat_id,
            participants_count=next_count,
            source=source,
            observed_at=observed_at,
        )

    async def _resolve_joined_dates(self, client, chat_id: str, user_ids: list[int]) -> dict[int, Optional[datetime]]:
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
        from telethon import events
        from telethon.tl import types

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
