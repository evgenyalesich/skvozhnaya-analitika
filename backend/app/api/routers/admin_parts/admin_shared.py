# Разделяемые хелперы для admin-роутеров.

from fastapi import HTTPException

from app.services.marketing_daily_service import MarketingDailyAccessError, MarketingDailyService


def require_marketing_daily_admin(user: dict) -> int:
    # Проверяет, что tg_user_id текущего пользователя есть в списке admins Marketing Daily.
    # При отказе поднимает HTTP 403. Возвращает tg_user_id для дальнейшего логирования.
    tg_user_id = int(user.get("tg_user_id") or 0)
    try:
        MarketingDailyService().assert_admin(tg_user_id)
    except MarketingDailyAccessError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    return tg_user_id
