import re
import time
import uuid
from typing import Any, Dict, Optional, Tuple

import asyncpg
import jwt
import httpx

from app.core.config import settings
from app.core.redis_client import RedisCache


class TelegramAuthService:
    def __init__(self) -> None:
        self._redis = RedisCache()

    async def create_start_token(self) -> str:
        token = uuid.uuid4().hex
        await self._redis.set_json(
            f"auth:start:{token}",
            {"created_at": int(time.time())},
            ttl=settings.auth_start_token_ttl_seconds,
        )
        return token

    async def validate_start_token(self, token: str) -> bool:
        payload = await self._redis.get_json(f"auth:start:{token}")
        return payload is not None

    async def consume_start_token(self, token: str) -> None:
        await self._redis.set_json(f"auth:start:{token}", None, ttl=1)

    async def store_start_result(self, token: str, payload: Dict[str, Any]) -> None:
        await self._redis.set_json(
            f"auth:start_result:{token}",
            payload,
            ttl=settings.auth_start_token_ttl_seconds,
        )

    async def get_start_result(self, token: str) -> Optional[Dict[str, Any]]:
        return await self._redis.get_json(f"auth:start_result:{token}")

    async def store_pending(self, token: str, payload: Dict[str, Any]) -> None:
        await self._redis.set_json(
            f"auth:pending:{token}",
            payload,
            ttl=settings.auth_start_token_ttl_seconds,
        )

    async def get_pending(self, token: str) -> Optional[Dict[str, Any]]:
        return await self._redis.get_json(f"auth:pending:{token}")

    async def clear_pending(self, token: str) -> None:
        await self._redis.set_json(f"auth:pending:{token}", None, ttl=1)

    async def user_exists_in_lead(self, tg_user_id: int) -> bool:
        if not settings.lead_db_dsn:
            return True
        dsn = str(settings.lead_db_dsn).replace("postgresql+asyncpg://", "postgresql://")
        conn = await asyncpg.connect(dsn)
        try:
            row = await conn.fetchrow("SELECT id FROM users WHERE id=$1 LIMIT 1", tg_user_id)
            return row is not None
        finally:
            await conn.close()

    def build_login_link(self, start_token: str) -> str:
        bot_name = settings.telegram_bot_username or "pokerhub_robot"
        bot_name = bot_name.lstrip("@")
        return f"https://t.me/{bot_name}?start=rs_{start_token}"

    def create_session_jwt(self, tg_user_id: int, username: Optional[str]) -> str:
        if not settings.auth_jwt_secret:
            raise ValueError("AUTH_JWT_SECRET is not configured")
        now = int(time.time())
        payload = {
            "sub": str(tg_user_id),
            "username": username or "",
            "iat": now,
            "exp": now + settings.auth_session_ttl_seconds,
        }
        return jwt.encode(payload, settings.auth_jwt_secret, algorithm="HS256")

    async def store_session(self, token: str, user: Dict[str, Any]) -> None:
        await self._redis.set_json(
            f"auth:session:{token}",
            user,
            ttl=settings.auth_session_ttl_seconds,
        )

    async def get_session(self, token: str) -> Optional[Dict[str, Any]]:
        return await self._redis.get_json(f"auth:session:{token}")

    async def notify_success(self, tg_user_id: int) -> None:
        if not settings.telegram_bot_token:
            return
        url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(
                url,
                json={
                    "chat_id": tg_user_id,
                    "text": "Вход подтвержден. Вернитесь на сайт.",
                },
            )

    async def send_auth_request(self, tg_user_id: int, username: Optional[str], start_token: str) -> None:
        if not settings.telegram_bot_token:
            return
        url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
        display_name = username or "пользователь"
        text = (
            f'Вы входите на сайт roistat.pokerhub.pro под учетной записью "{display_name}".\n\n'
            'Чтобы подтвердить вход, нажмите кнопку "Авторизоваться".\n'
            'Если это не вы — нажмите "Отмена".'
        )
        reply_markup = {
            "inline_keyboard": [
                [
                    {"text": "Авторизоваться", "callback_data": f"auth:approve:{start_token}"},
                    {"text": "Отмена", "callback_data": f"auth:deny:{start_token}"},
                ]
            ]
        }
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(
                url,
                json={
                    "chat_id": tg_user_id,
                    "text": text,
                    "reply_markup": reply_markup,
                },
            )

    async def send_message(self, tg_user_id: int, text: str) -> None:
        if not settings.telegram_bot_token:
            return
        url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(url, json={"chat_id": tg_user_id, "text": text})

    async def answer_callback(self, callback_id: str, text: str) -> None:
        if not settings.telegram_bot_token:
            return
        url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/answerCallbackQuery"
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(
                url,
                json={"callback_query_id": callback_id, "text": text, "show_alert": False},
            )

    @staticmethod
    def parse_callback(data: str) -> Optional[Tuple[str, str]]:
        if not data.startswith("auth:"):
            return None
        parts = data.split(":", 2)
        if len(parts) != 3:
            return None
        return parts[1], parts[2]

    @staticmethod
    def extract_start_token(text: str) -> Optional[str]:
        match = re.match(r"^/start\\s+(.+)$", text.strip())
        if not match:
            return None
        payload = match.group(1).strip()
        if payload.startswith("rs_"):
            return payload[3:]
        if payload.startswith("roistat_"):
            return payload[8:]
        return payload
