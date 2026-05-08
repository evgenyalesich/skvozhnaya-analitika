import os
import time
import logging
import requests
from typing import List, Optional, Dict

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from redis import Redis
from app.core.config import settings
from app.core.redis_client import RedisCache
from app.models.analytics import RawBotUser, TelegramSubscriptionEvent


class TelegramStatusIngestor:
    def __init__(self, loader=None):
        # loader оставлен для совместимости, но сейчас используем env напрямую
        self.loader = loader
        self.cache = RedisCache()
        self._logger = logging.getLogger("telegram_ingestor")
        self.redis = Redis.from_url(str(settings.redis_url))

    async def fetch_user_ids(self, session: AsyncSession) -> List[int]:
        stmt = select(RawBotUser.tg_user_id).distinct()
        result = await session.execute(stmt)
        raw_ids = [user for user in result.scalars().all() if user]
        user_ids: List[int] = []
        for raw_id in raw_ids:
            try:
                user_ids.append(int(raw_id))
            except (TypeError, ValueError):
                continue
        return user_ids

    async def ingest(self, session: AsyncSession, user_ids: Optional[List[int]] = None) -> None:
        token = os.environ.get("TELEGRAM_BOT_TOKEN")
        if not token:
            self._logger.warning("Telegram ingest skipped: TELEGRAM_BOT_TOKEN is not set")
            return
        channel_id = os.environ.get("TELEGRAM_CHANNEL_ID")
        community_id = os.environ.get("TELEGRAM_COMMUNITY_ID")
        if community_id and not str(community_id).lstrip("-").isdigit():
            community_id = None
        if not channel_id and not community_id:
            self._logger.warning("Telegram ingest skipped: no TELEGRAM_CHANNEL_ID/COMMUNITY_ID")
            return
        bot_id = self._fetch_bot_id(token)
        if bot_id is None:
            self._logger.warning("Telegram ingest skipped: unable to resolve bot id via getMe")
            return
        if channel_id and not self._is_bot_admin(token, channel_id, bot_id):
            self._logger.warning("Telegram ingest skipped: bot is not admin of channel_id=%s", channel_id)
            channel_id = None
        if community_id and not self._is_bot_admin(token, community_id, bot_id):
            self._logger.warning("Telegram ingest skipped: bot is not admin of community_id=%s", community_id)
            community_id = None
        if not channel_id and not community_id:
            return
        if channel_id:
            self._logger.info("Telegram ingest: checking channel_id=%s", channel_id)
        if community_id:
            self._logger.info("Telegram ingest: checking saloon_id=%s", community_id)
        if user_ids is None:
            stmt = select(RawBotUser.tg_user_id).distinct()
            result = await session.execute(stmt)
            raw_ids = [user for user in result.scalars().all() if user]
            user_ids = []
            for raw_id in raw_ids:
                try:
                    user_ids.append(int(raw_id))
                except (TypeError, ValueError):
                    # пропускаем некорректные id
                    continue
        if not user_ids:
            return
        self._logger.info(
            "Telegram ingest: batch size=%s channel_id=%s community_id=%s",
            len(user_ids),
            channel_id or "none",
            community_id or "none",
        )
        current_status_map = {}
        status_stmt = select(
            RawBotUser.tg_user_id,
            RawBotUser.channel_subscribed,
            RawBotUser.community_member,
        )
        status_result = await session.execute(status_stmt)
        community_status_map = {}
        for tg_user_id, channel_subscribed, community_member in status_result.all():
            if tg_user_id is not None:
                current_status_map[int(tg_user_id)] = channel_subscribed
                community_status_map[int(tg_user_id)] = community_member
        # Process all users in a single run (limits removed as requested).
        batch_size = len(user_ids)
        # Используем прямой HTTP вызов к Bot API (стабильнее в нашем окружении)
        api_base = f"https://api.telegram.org/bot{token}"
        channel_map: Dict[int, Optional[bool]] = {}
        community_map: Dict[int, Optional[bool]] = {}
        start = time.monotonic()
        events: List[TelegramSubscriptionEvent] = []
        checked = 0
        subscribed = 0
        unsubscribed = 0
        community_subscribed = 0
        community_unsubscribed = 0
        events_count = 0
        invalid_ids = 0
        not_found = 0
        log_every = 50
        pending_updates: List[tuple[int, Optional[bool], Optional[bool]]] = []

        def build_update_stmt():
            if not pending_updates:
                return
            # bulk update with COALESCE to avoid overwriting with NULL
            values_sql = ",".join(
                f"(CAST(:tg_user_id_{i} AS BIGINT), CAST(:channel_subscribed_{i} AS BOOLEAN), CAST(:community_member_{i} AS BOOLEAN))"
                for i in range(len(pending_updates))
            )
            params = {}
            for i, (uid, ch, cm) in enumerate(pending_updates):
                params[f"tg_user_id_{i}"] = uid
                params[f"channel_subscribed_{i}"] = ch
                params[f"community_member_{i}"] = cm
            stmt = text(
                f"""
                UPDATE raw_bot_users AS r
                SET
                    channel_subscribed = COALESCE(v.channel_subscribed, r.channel_subscribed),
                    community_member = COALESCE(v.community_member, r.community_member)
                FROM (VALUES {values_sql}) AS v(tg_user_id, channel_subscribed, community_member)
                WHERE r.tg_user_id = v.tg_user_id
                """
            )
            return stmt, params

        for user_id in user_ids:
            channel_subscribed, channel_status = self._check_membership(api_base, channel_id, user_id)
            community_member, community_status = self._check_membership(api_base, community_id, user_id)
            if channel_status == "invalid":
                invalid_ids += 1
            elif channel_status == "not_found":
                not_found += 1
            if channel_subscribed is not None:
                channel_map[int(user_id)] = channel_subscribed
                prev_status = current_status_map.get(int(user_id))
                if prev_status is None or bool(prev_status) != bool(channel_subscribed):
                    events.append(
                        TelegramSubscriptionEvent(
                            tg_user_id=int(user_id),
                            channel_id=str(channel_id),
                            status="subscribed" if channel_subscribed else "unsubscribed",
                            source="bot_poll",
                        )
                    )
                    events_count += 1
                if channel_subscribed:
                    subscribed += 1
                else:
                    unsubscribed += 1
            if community_member is not None:
                community_map[int(user_id)] = community_member
                prev_community = community_status_map.get(int(user_id))
                if prev_community is None or bool(prev_community) != bool(community_member):
                    events.append(
                        TelegramSubscriptionEvent(
                            tg_user_id=int(user_id),
                            channel_id=str(community_id),
                            status="subscribed" if community_member else "unsubscribed",
                            source="bot_poll",
                        )
                    )
                    events_count += 1
                if community_member:
                    community_subscribed += 1
                else:
                    community_unsubscribed += 1
            if channel_subscribed is not None or community_member is not None:
                pending_updates.append((int(user_id), channel_subscribed, community_member))
            checked += 1
            if checked % log_every == 0:
                elapsed = time.monotonic() - start
                rate = checked / elapsed if elapsed else 0
                remaining = len(user_ids) - checked
                eta = remaining / rate if rate else 0
                total_users = int(self.redis.get("telegram:users:total") or 0)
                checked_total = int(self.redis.get("telegram:users:checked") or 0)
                overall_checked = checked_total + checked
                if total_users:
                    overall_checked = min(overall_checked, total_users)
                self._logger.info(
                    "Telegram ingest progress: batch_checked=%s/%s overall_checked=%s/%s channel_sub=%s channel_unsub=%s saloon_sub=%s saloon_unsub=%s events=%s elapsed=%.1fs eta=%.1fs",
                    checked,
                    len(user_ids),
                    overall_checked if total_users else checked,
                    total_users if total_users else len(user_ids),
                    subscribed,
                    unsubscribed,
                    community_subscribed,
                    community_unsubscribed,
                    events_count,
                    elapsed,
                    eta,
                )
            if len(pending_updates) >= 200:
                try:
                    stmt_pack = build_update_stmt()
                    if stmt_pack:
                        stmt, params = stmt_pack
                        await session.execute(stmt, params)
                        pending_updates.clear()
                except Exception:
                    self._logger.exception("Telegram ingest: bulk update failed, retrying batch")
                    await session.rollback()
                    time.sleep(0.5)
                    if pending_updates:
                        stmt, params = build_update_stmt()
                        await session.execute(stmt, params)
                        pending_updates.clear()
        if pending_updates:
            stmt, params = build_update_stmt()
            await session.execute(stmt, params)
            pending_updates.clear()
        if events:
            session.add_all(events)
        self._logger.info(
            "Telegram ingest: checked=%s channel_sub=%s channel_unsub=%s saloon_sub=%s saloon_unsub=%s events=%s invalid_ids=%s not_found=%s",
            checked,
            subscribed,
            unsubscribed,
            community_subscribed,
            community_unsubscribed,
            events_count,
            invalid_ids,
            not_found,
        )
        # Кэшируем результат, чтобы отчеты тянулись мгновенно
        ttl = settings.cache_ttl_seconds
        if channel_id and channel_map:
            await self.cache.set_json(f"telegram:channel:{channel_id}", channel_map, ttl=ttl)
        if community_id and community_map:
            await self.cache.set_json(f"telegram:community:{community_id}", community_map, ttl=ttl)

    def _check_membership(self, api_base: str, chat_id: str, user_id: int) -> tuple[Optional[bool], Optional[str]]:
        if not chat_id:
            return None, None
        attempts = 3
        for attempt in range(1, attempts + 1):
            try:
                resp = requests.get(
                    f"{api_base}/getChatMember",
                    params={"chat_id": chat_id, "user_id": user_id},
                    timeout=8,
                )
                data = resp.json()
                if not data.get("ok"):
                    # не перезаписываем, если не смогли проверить
                    desc_raw = str(data.get("description", ""))
                    desc = desc_raw.upper()
                    if "PARTICIPANT_ID_INVALID" in desc:
                        return False, "invalid"
                    if "MEMBER NOT FOUND" in desc:
                        return False, "not_found"
                    self._logger.warning(
                        "Telegram ingest: getChatMember failed chat_id=%s user_id=%s error=%s",
                        chat_id,
                        user_id,
                        data.get("description"),
                    )
                    return None, "error"
                status = data.get("result", {}).get("status", "")
                return status not in ("left", "kicked"), "ok"
            except requests.RequestException as exc:
                if attempt == attempts:
                    self._logger.exception(
                        "Telegram ingest: request error chat_id=%s user_id=%s", chat_id, user_id
                    )
                    return None, "error"
                self._logger.warning(
                    "Telegram ingest: retry %s/%s chat_id=%s user_id=%s error=%s",
                    attempt,
                    attempts,
                    chat_id,
                    user_id,
                    exc,
                )
                time.sleep(1.0 * attempt)

    def _fetch_bot_id(self, token: str) -> Optional[int]:
        try:
            resp = requests.get(
                f"https://api.telegram.org/bot{token}/getMe",
                timeout=5,
            )
            data = resp.json()
            if not data.get("ok"):
                self._logger.warning("Telegram ingest: getMe failed error=%s", data.get("description"))
                return None
            bot_id = data.get("result", {}).get("id")
            return int(bot_id) if bot_id else None
        except requests.RequestException:
            self._logger.exception("Telegram ingest: getMe request error")
            return None

    def _is_bot_admin(self, token: str, chat_id: str, bot_id: int) -> bool:
        try:
            resp = requests.get(
                f"https://api.telegram.org/bot{token}/getChatMember",
                params={"chat_id": chat_id, "user_id": bot_id},
                timeout=5,
            )
            data = resp.json()
            if not data.get("ok"):
                self._logger.warning(
                    "Telegram ingest: getChatMember(bot) failed chat_id=%s error=%s",
                    chat_id,
                    data.get("description"),
                )
                return False
            status = data.get("result", {}).get("status", "")
            return status in ("administrator", "creator")
        except requests.RequestException:
            self._logger.exception("Telegram ingest: getChatMember(bot) request error chat_id=%s", chat_id)
            return False
