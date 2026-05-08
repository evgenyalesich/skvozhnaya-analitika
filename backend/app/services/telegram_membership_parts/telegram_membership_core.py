from __future__ import annotations

import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import BASE_DIR, settings
from app.db.session import async_session
from app.models.analytics import TelegramChatMembership, TelegramChatTotal, TelegramSubscriptionEvent
from app.services.system_settings_service import SyncEventLogger

logger = logging.getLogger(__name__)


@dataclass
class MembershipSyncStats:
    added: int = 0
    removed: int = 0
    unchanged: int = 0
    looked_up: int = 0


@dataclass
class ChatMembersSnapshot:
    chat_id: str
    members: set[int]
    fetched_at: datetime


class TelegramMembershipCoreMixin:
    """Ядро сервиса членства в Telegram-чатах.

    Отвечает за:
    - подключение MTProto-клиента (Telethon) с проверкой авторизации
    - полное сканирование участников чата (2 стадии: Recent + буквенный поиск)
    - upsert/update счётчика участников (TelegramChatTotal)
    """

    def __init__(self) -> None:
        self._logger = logging.getLogger("telegram_membership_service")

    def configured_chat_ids(self) -> list[str]:
        """Возвращает список chat_id из settings + из env TELEGRAM_CHANNEL_ID / TELEGRAM_COMMUNITY_ID."""
        configured = list(settings.telegram_membership_chat_ids)
        for env_name in ("TELEGRAM_CHANNEL_ID", "TELEGRAM_COMMUNITY_ID"):
            value = os.getenv(env_name)
            if value and value not in configured:
                configured.append(value)
        return configured

    def ensure_configured(self) -> None:
        """Проверяет наличие API_ID/API_HASH и chat_id. Кидает RuntimeError если не настроено."""
        if not settings.telegram_api_id or not settings.telegram_api_hash:
            raise RuntimeError("TELEGRAM_API_ID/TELEGRAM_API_HASH are not configured")
        if not self.configured_chat_ids():
            raise RuntimeError("No Telegram membership chat ids configured")

    @asynccontextmanager
    async def mtproto_client(self):
        """Контекстный менеджер: открывает Telethon-клиент, проверяет авторизацию, закрывает по выходу.

        Сессия хранится в файле settings.telegram_mtproto_session_name.
        Авторизацию нужно пройти вручную один раз перед запуском (интерактивный логин).
        """
        try:
            from telethon import TelegramClient
        except ImportError as exc:
            raise RuntimeError("Telethon is not installed. Run pip install -r backend/requirements.txt") from exc

        session_name = str(BASE_DIR / settings.telegram_mtproto_session_name)
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
        """Полное сканирование участников чата через Telegram MTProto API.

        Стадия 1 (Recent): пагинация GetParticipantsRecent — собирает до ~200 последних.
        Стадия 2 (Search): буквенный перебор (a-z, а-я, 0-9, спецсимволы) через
            GetParticipantsSearch — находит тех, кого не поймала стадия 1.
        Если collected >= expected — стадия 2 пропускается.
        После сбора: опционально резолвит joined_at для пользователей без даты вступления.
        """
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
        # INSERT ... ON CONFLICT DO UPDATE — обновляет счётчик участников для чата.
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
        # Инкрементально изменяет счётчик участников на delta (±1).
        # Используется при realtime-событиях, чтобы не делать полный пересчёт.
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
