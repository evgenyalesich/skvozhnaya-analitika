import asyncio
import os
from typing import Set, List, Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from telegram import Bot
from telegram.error import TelegramError

from app.core.config_loader import ConfigLoader
from app.models.analytics import RawBotUser


class TelegramStatusIngestor:
    def __init__(self, loader: ConfigLoader):
        self.loader = loader

    async def ingest(self, session: AsyncSession) -> None:
        config = self.loader.data_sources().get("telegram_api", {})
        token = os.environ.get(config.get("bot_token_env", ""))
        if not token:
            return
        channel_id = os.environ.get(config.get("channel_id_env", ""))
        community_id = os.environ.get(config.get("community_id_env", ""))
        stmt = select(RawBotUser.tg_user_id).distinct()
        result = await session.execute(stmt)
        user_ids = [user for user in result.scalars().all() if user]
        if not user_ids:
            return
        bot = Bot(token=token)
        async with bot:
            for user_id in user_ids:
                channel_subscribed = await self._check_membership(bot, channel_id, user_id)
                community_member = await self._check_membership(bot, community_id, user_id)
                values = {}
                if channel_subscribed is not None:
                    values["channel_subscribed"] = channel_subscribed
                if community_member is not None:
                    values["community_member"] = community_member
                if values:
                    stmt = update(RawBotUser).where(RawBotUser.tg_user_id == user_id).values(**values)
                    await session.execute(stmt)

    async def _check_membership(self, bot: Bot, chat_id: str, user_id: int) -> Optional[bool]:
        if not chat_id:
            return None
        try:
            member = await bot.get_chat_member(int(chat_id), user_id)
            return member.status not in ("left", "kicked")
        except TelegramError:
            return False
