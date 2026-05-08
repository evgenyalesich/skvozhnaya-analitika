from typing import List

from fastapi import APIRouter, Depends, HTTPException

from app.api.dependencies import get_current_user, get_db_session
from app.schemas.system_settings import (
    MarketingDailyPreviewOut,
    MarketingDailySettings,
    MarketingDailySettingsUpdate,
    SystemSettingsOut,
    SystemSettingsUpdate,
    SyncEventLogOut,
)
from app.services.marketing_daily_service import MarketingDailyDeliveryError, MarketingDailyService
from app.services.system_settings_service import SystemSettingsService

from .admin_shared import require_marketing_daily_admin

# Эндпоинты управления системными настройками и Marketing Daily дайджестом.
# Все marketing-daily эндпоинты требуют require_marketing_daily_admin (tg_user_id в списке admins).

router = APIRouter()


@router.get("/settings", response_model=SystemSettingsOut)
# Читает настройки планировщика из SystemSetting (таблица system_settings).
async def get_system_settings(session=Depends(get_db_session)):
    return await SystemSettingsService().get_settings(session)


@router.put("/settings", response_model=SystemSettingsOut)
async def update_system_settings(payload: SystemSettingsUpdate, session=Depends(get_db_session)):
    result = await SystemSettingsService().update_settings(session, payload.scheduler.model_dump())
    await session.commit()
    return result


@router.get("/sync-logs", response_model=List[SyncEventLogOut])
async def list_sync_logs(limit: int = 100, session=Depends(get_db_session)):
    rows = await SystemSettingsService().list_logs(session, limit=limit)
    return [SyncEventLogOut.model_validate(row) for row in rows]


@router.get("/marketing-daily/settings", response_model=MarketingDailySettings)
async def get_marketing_daily_settings(user: dict = Depends(get_current_user), session=Depends(get_db_session)):
    require_marketing_daily_admin(user)
    settings_payload = await MarketingDailyService().get_settings(session)
    return MarketingDailySettings.model_validate(settings_payload)


@router.put("/marketing-daily/settings", response_model=MarketingDailySettings)
async def update_marketing_daily_settings(
    payload: MarketingDailySettingsUpdate,
    user: dict = Depends(get_current_user),
    session=Depends(get_db_session),
):
    require_marketing_daily_admin(user)
    try:
        settings_payload = await MarketingDailyService().update_settings(
            session,
            payload.marketing_daily.model_dump(),
        )
        await session.commit()
        return MarketingDailySettings.model_validate(settings_payload)
    except MarketingDailyDeliveryError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/marketing-daily/preview", response_model=MarketingDailyPreviewOut)
# Формирует дайджест (build_digest) без отправки — для предпросмотра в admin UI.
async def preview_marketing_daily(user: dict = Depends(get_current_user), session=Depends(get_db_session)):
    require_marketing_daily_admin(user)
    payload = await MarketingDailyService().build_digest(session)
    return MarketingDailyPreviewOut.model_validate(payload)


@router.post("/marketing-daily/send-test")
# Принудительная отправка (force=True — игнорирует ограничение одной отправки в день).
async def send_marketing_daily_test(user: dict = Depends(get_current_user), session=Depends(get_db_session)):
    requester_user_id = require_marketing_daily_admin(user)
    try:
        return await MarketingDailyService().send_digest(session, initiated_by=requester_user_id, force=True)
    except MarketingDailyDeliveryError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/marketing-daily/history")
async def marketing_daily_history(limit: int = 20, user: dict = Depends(get_current_user)):
    require_marketing_daily_admin(user)
    try:
        return {"items": await MarketingDailyService().fetch_delivery_history(limit=limit)}
    except MarketingDailyDeliveryError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/marketing-daily/resend")
async def resend_marketing_daily(user: dict = Depends(get_current_user), session=Depends(get_db_session)):
    requester_user_id = require_marketing_daily_admin(user)
    try:
        return await MarketingDailyService().send_digest(session, initiated_by=requester_user_id, force=True)
    except MarketingDailyDeliveryError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
