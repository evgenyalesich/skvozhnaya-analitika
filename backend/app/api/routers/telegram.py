from typing import Any, Dict, Optional

from fastapi import APIRouter, Header, HTTPException

from app.core.config import settings
from app.services.telegram_auth import TelegramAuthService

router = APIRouter()


@router.post("/api/telegram/webhook")
async def telegram_webhook(
    update: Dict[str, Any],
    x_telegram_bot_api_secret_token: Optional[str] = Header(default=None),
):
    if settings.telegram_webhook_secret:
        if x_telegram_bot_api_secret_token != settings.telegram_webhook_secret:
            raise HTTPException(status_code=401, detail="Invalid webhook secret")

    callback = update.get("callback_query")
    if callback:
        data = callback.get("data") or ""
        parsed = TelegramAuthService.parse_callback(data)
        if not parsed:
            return {"ok": True}

        action, start_token = parsed
        user = callback.get("from") or {}
        tg_user_id = user.get("id")
        callback_id = callback.get("id")
        if not tg_user_id or not callback_id:
            return {"ok": True}

        service = TelegramAuthService()
        pending = await service.get_pending(start_token)
        if not pending or int(pending.get("tg_user_id", 0)) != int(tg_user_id):
            await service.answer_callback(callback_id, "Сессия истекла или недействительна")
            return {"ok": True}

        if action == "deny":
            await service.store_start_result(start_token, {"error": "denied"})
            await service.consume_start_token(start_token)
            await service.clear_pending(start_token)
            await service.answer_callback(callback_id, "Авторизация отменена")
            await service.send_message(tg_user_id, "Авторизация отменена.")
            return {"ok": True}

        if action == "approve":
            if not await service.validate_start_token(start_token):
                await service.answer_callback(callback_id, "Сессия истекла")
                return {"ok": True}
            if not settings.auth_allow_unknown_users:
                exists = await service.user_exists_in_lead(tg_user_id)
                if not exists:
                    await service.answer_callback(callback_id, "Пользователь не найден")
                    await service.send_message(tg_user_id, "Пользователь не найден в базе lead.")
                    return {"ok": True}

            access_token = service.create_session_jwt(tg_user_id, user.get("username"))
            await service.store_session(
                access_token,
                {"tg_user_id": tg_user_id, "username": user.get("username")},
            )
            await service.store_start_result(
                start_token,
                {"access_token": access_token, "tg_user_id": tg_user_id, "username": user.get("username")},
            )
            await service.consume_start_token(start_token)
            await service.clear_pending(start_token)
            await service.answer_callback(callback_id, "Авторизация подтверждена")
            await service.notify_success(tg_user_id)
            return {"ok": True}

        await service.answer_callback(callback_id, "Неизвестная команда")
        return {"ok": True}

    message = update.get("message") or update.get("edited_message")
    if not message:
        return {"ok": True}

    text = message.get("text") or ""
    start_token = TelegramAuthService.extract_start_token(text)
    if not start_token:
        return {"ok": True}

    user = message.get("from") or {}
    tg_user_id = user.get("id")
    if not tg_user_id:
        return {"ok": True}

    service = TelegramAuthService()
    if not await service.validate_start_token(start_token):
        return {"ok": True}

    if not settings.auth_allow_unknown_users:
        exists = await service.user_exists_in_lead(tg_user_id)
        if not exists:
            await service.store_start_result(start_token, {"error": "not_registered"})
            await service.consume_start_token(start_token)
            await service.send_message(tg_user_id, "Пользователь не найден в базе lead.")
            return {"ok": True}

    await service.store_pending(
        start_token,
        {"tg_user_id": tg_user_id, "username": user.get("username")},
    )
    await service.send_auth_request(tg_user_id, user.get("username"), start_token)
    return {"ok": True}
