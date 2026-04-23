from typing import List
from datetime import date

from fastapi import APIRouter, Depends, HTTPException

from app.api.dependencies import get_access_service, get_current_user, get_db_session
from sqlalchemy import text
from app.db.postgres_explorer import PostgresExplorer
from app.schemas.db_explorer import DatabaseListResponse, DatabaseQueryRequest, DatabaseQueryResponse
from app.schemas.employee_registry import (
    EmployeeRegistryBulkCreate,
    EmployeeRegistryCreate,
    EmployeeRegistryOut,
    EmployeeRegistryReplace,
)
from app.schemas.telegram_access import TelegramAccessCreate, TelegramAccessOut
from app.services.employee_registry_service import EmployeeRegistryService
from app.services.telegram_access_service import TelegramAccessService
from app.services.system_settings_service import SystemSettingsService
from app.schemas.system_settings import (
    MarketingDailyPreviewOut,
    MarketingDailySettings,
    MarketingDailySettingsUpdate,
    SystemSettingsOut,
    SystemSettingsUpdate,
    SyncEventLogOut,
)
from app.services.marketing_daily_service import (
    MarketingDailyAccessError,
    MarketingDailyDeliveryError,
    MarketingDailyService,
)
from app.worker.tasks import (
    queue,
    schedule_aggregation_job,
    schedule_google_sheets_job,
    schedule_ingestion_job,
    schedule_pokerhub_cache_job,
    schedule_roistat_weekly_export_job,
    schedule_telegram_job,
    schedule_telegram_membership_full_sync_job,
    schedule_telegram_membership_realtime_job,
)
from app.core.redis_client import RedisCache

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _require_marketing_daily_admin(user: dict) -> int:
    tg_user_id = int(user.get("tg_user_id") or 0)
    try:
        MarketingDailyService().assert_admin(tg_user_id)
    except MarketingDailyAccessError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    return tg_user_id


@router.post("/ingest")
def trigger_ingest():
    schedule_ingestion_job()
    return {"status": "ok", "message": "Ingestion job queued"}


@router.post("/sync-pokerhub")
def sync_pokerhub():
    schedule_pokerhub_cache_job()
    return {"status": "ok", "source": "pokerhub", "message": "Обновление кэша PokerHub запущено"}


@router.post("/sync-google-sheets")
def sync_google_sheets():
    schedule_google_sheets_job()
    return {"status": "ok", "source": "google_sheets", "message": "Синхронизация Google Sheets запущена"}


@router.post("/sync-mongodb")
def sync_mongodb():
    schedule_ingestion_job()
    return {"status": "ok", "source": "mongodb", "message": "Синхронизация MongoDB запущена"}


@router.post("/sync-telegram")
def sync_telegram():
    schedule_telegram_job()
    return {"status": "ok", "source": "telegram", "message": "Синхронизация Telegram API запущена"}


@router.post("/sync-telegram-membership")
def sync_telegram_membership():
    schedule_telegram_membership_full_sync_job()
    return {
        "status": "ok",
        "source": "telegram_membership",
        "message": "Полный sync membership Telegram поставлен в очередь",
    }


@router.post("/start-telegram-membership-realtime")
def start_telegram_membership_realtime():
    schedule_telegram_membership_realtime_job()
    return {
        "status": "ok",
        "source": "telegram_membership_realtime",
        "message": "Realtime monitoring membership Telegram поставлен в очередь",
    }


@router.post("/sync-roistat-weekly")
def sync_roistat_weekly(first_touch_start: str | None = None, first_touch_end: str | None = None):
    # Accept ISO dates (YYYY-MM-DD). If omitted, export without cohort filtering.
    if first_touch_start:
        try:
            date.fromisoformat(first_touch_start)
        except ValueError:
            raise HTTPException(status_code=400, detail="first_touch_start must be YYYY-MM-DD")
    if first_touch_end:
        try:
            date.fromisoformat(first_touch_end)
        except ValueError:
            raise HTTPException(status_code=400, detail="first_touch_end must be YYYY-MM-DD")
    schedule_roistat_weekly_export_job(first_touch_start=first_touch_start, first_touch_end=first_touch_end)
    return {"status": "ok", "source": "roistat_weekly", "message": "Экспорт Weekly в Google Sheets запущен"}


@router.post("/sync-advertising-budget")
def sync_advertising_budget():
    schedule_ingestion_job()
    return {"status": "ok", "source": "advertising", "message": "Синхронизация бюджета запущена"}


@router.post("/sync-all")
async def sync_all():
    schedule_ingestion_job()
    cache = RedisCache()
    await cache.delete_pattern("utm:options:*")
    return {"status": "ok", "message": "Sync for all sources queued"}


@router.post("/refresh-agg")
def refresh_agg():
    schedule_aggregation_job()
    return {"status": "ok", "message": "Aggregate recalculation started"}


@router.get("/status")
def admin_status():
    return {
        "status": "idle",
        "pending_jobs": queue.count,
        "queue_name": queue.name,
    }


@router.get("/sync-status")
async def sync_status():
    cache = RedisCache()
    last_ingestion = await cache.get_json("sync:last_ingestion")
    last_sm = await cache.get_json("sync:last_sm")
    last_ingestion_success = await cache.get_json("sync:last_ingestion_success")
    last_roistat_weekly = await cache.get_json("sync:last_roistat_weekly")
    last_roistat_weekly_success = await cache.get_json("sync:last_roistat_weekly_success")
    return {
        "last_ingestion": last_ingestion or None,
        "last_ingestion_success": last_ingestion_success or None,
        "last_sm": last_sm or None,
        "last_roistat_weekly": last_roistat_weekly or None,
        "last_roistat_weekly_success": last_roistat_weekly_success or None,
    }


@router.get("/settings", response_model=SystemSettingsOut)
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
async def get_marketing_daily_settings(
    user: dict = Depends(get_current_user),
    session=Depends(get_db_session),
):
    _require_marketing_daily_admin(user)
    settings_payload = await MarketingDailyService().get_settings(session)
    return MarketingDailySettings.model_validate(settings_payload)


@router.put("/marketing-daily/settings", response_model=MarketingDailySettings)
async def update_marketing_daily_settings(
    payload: MarketingDailySettingsUpdate,
    user: dict = Depends(get_current_user),
    session=Depends(get_db_session),
):
    _require_marketing_daily_admin(user)
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
async def preview_marketing_daily(
    user: dict = Depends(get_current_user),
    session=Depends(get_db_session),
):
    _require_marketing_daily_admin(user)
    payload = await MarketingDailyService().build_digest(session)
    return MarketingDailyPreviewOut.model_validate(payload)


@router.post("/marketing-daily/send-test")
async def send_marketing_daily_test(
    user: dict = Depends(get_current_user),
    session=Depends(get_db_session),
):
    requester_user_id = _require_marketing_daily_admin(user)
    try:
        result = await MarketingDailyService().send_digest(session, initiated_by=requester_user_id, force=True)
        return result
    except MarketingDailyDeliveryError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/marketing-daily/history")
async def marketing_daily_history(
    limit: int = 20,
    user: dict = Depends(get_current_user),
):
    _require_marketing_daily_admin(user)
    try:
        return {"items": await MarketingDailyService().fetch_delivery_history(limit=limit)}
    except MarketingDailyDeliveryError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/marketing-daily/resend")
async def resend_marketing_daily(
    user: dict = Depends(get_current_user),
    session=Depends(get_db_session),
):
    requester_user_id = _require_marketing_daily_admin(user)
    try:
        return await MarketingDailyService().send_digest(session, initiated_by=requester_user_id, force=True)
    except MarketingDailyDeliveryError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/data-sources-status")
def data_sources_status():
    return {"sources": {"postgres": "ok", "google_sheets": "pending"}}


@router.get("/databases", response_model=DatabaseListResponse)
async def list_databases():
    explorer = PostgresExplorer()
    databases = await explorer.list_databases()
    return DatabaseListResponse(databases=databases)


@router.get("/bot-databases", response_model=DatabaseListResponse)
async def list_bot_databases():
    explorer = PostgresExplorer()
    databases = await explorer.list_bot_databases()
    return DatabaseListResponse(databases=databases)


@router.post("/query-db", response_model=DatabaseQueryResponse)
async def query_database(payload: DatabaseQueryRequest):
    explorer = PostgresExplorer()
    try:
        rows = await explorer.execute_query(payload.database, payload.query, payload.limit)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))
    return DatabaseQueryResponse(rows=rows)


@router.get("/telegram-access", response_model=List[TelegramAccessOut])
async def list_telegram_access(
    _user: dict = Depends(get_current_user),
    service: TelegramAccessService = Depends(get_access_service),
):
    entries = await service.list_access()
    return [TelegramAccessOut.from_orm(entry) for entry in entries]


@router.post("/telegram-access", response_model=TelegramAccessOut)
async def grant_telegram_access(
    payload: TelegramAccessCreate,
    user: dict = Depends(get_current_user),
    service: TelegramAccessService = Depends(get_access_service),
):
    entry = await service.grant_access(payload.tg_user_id, created_by=str(user.get("tg_user_id")))
    return TelegramAccessOut.from_orm(entry)


@router.delete("/telegram-access/{tg_user_id}")
async def revoke_telegram_access(
    tg_user_id: int,
    _user: dict = Depends(get_current_user),
    service: TelegramAccessService = Depends(get_access_service),
):
    await service.revoke_access(tg_user_id)
    return {"status": "ok"}


@router.get("/employee-registry", response_model=List[EmployeeRegistryOut])
async def list_employee_registry(_user: dict = Depends(get_current_user)):
    entries = await EmployeeRegistryService().list_entries()
    return [EmployeeRegistryOut.model_validate(entry) for entry in entries]


@router.post("/employee-registry", response_model=EmployeeRegistryOut)
async def add_employee_registry_entry(
    payload: EmployeeRegistryCreate,
    user: dict = Depends(get_current_user),
):
    entry = await EmployeeRegistryService().add_entry(payload.tg_user_id, created_by=str(user.get("tg_user_id")))
    schedule_aggregation_job()
    return EmployeeRegistryOut.model_validate(entry)


@router.post("/employee-registry/bulk")
async def add_employee_registry_entries(
    payload: EmployeeRegistryBulkCreate,
    user: dict = Depends(get_current_user),
):
    entries = await EmployeeRegistryService().add_entries(payload.tg_user_ids, created_by=str(user.get("tg_user_id")))
    if entries:
        schedule_aggregation_job()
    return {
        "status": "ok",
        "added": len(entries),
        "entries": [EmployeeRegistryOut.model_validate(entry).model_dump() for entry in entries],
    }


@router.delete("/employee-registry/{tg_user_id}")
async def remove_employee_registry_entry(
    tg_user_id: int,
    _user: dict = Depends(get_current_user),
):
    await EmployeeRegistryService().remove_entry(tg_user_id)
    schedule_aggregation_job()
    return {"status": "ok"}


@router.get("/utm-coverage")
async def utm_coverage(session=Depends(get_db_session)):
    """UTM мониторинг: все метки, покрытие, новые за последние 7 дней."""
    result = await session.execute(text("""
        WITH utm_data AS (
            SELECT
                COALESCE(platform_utm_source, utm_source)   AS source,
                COALESCE(platform_utm_campaign, utm_campaign) AS campaign,
                COUNT(*)                                     AS total_users,
                COUNT(*) FILTER (WHERE created_at >= NOW() - INTERVAL '7 days') AS new_7d,
                COUNT(*) FILTER (WHERE created_at >= NOW() - INTERVAL '1 day')  AS new_1d,
                MIN(created_at)                              AS first_seen,
                MAX(created_at)                              AS last_seen
            FROM raw_bot_users
            WHERE COALESCE(platform_utm_source, utm_source) IS NOT NULL
              AND COALESCE(platform_utm_source, utm_source) NOT IN ('', '(none)')
            GROUP BY 1, 2
        )
        SELECT
            source, campaign, total_users, new_7d, new_1d,
            first_seen, last_seen,
            CASE WHEN first_seen >= NOW() - INTERVAL '7 days' THEN true ELSE false END AS is_new
        FROM utm_data
        ORDER BY new_7d DESC, total_users DESC
    """))
    rows = result.fetchall()
    labels = [
        {
            "source": row[0],
            "campaign": row[1],
            "total_users": row[2],
            "new_7d": row[3],
            "new_1d": row[4],
            "first_seen": row[5].isoformat() if row[5] else None,
            "last_seen": row[6].isoformat() if row[6] else None,
            "is_new": row[7],
        }
        for row in rows
    ]
    return {
        "total_combinations": len(labels),
        "new_last_7d": sum(1 for l in labels if l["is_new"]),
        "labels": labels,
    }


@router.post("/utm-cache-clear")
async def utm_cache_clear():
    """Сбросить кэш UTM-опций — фильтры подтянут свежие данные."""
    cache = RedisCache()
    await cache.delete_pattern("utm:options:*")
    return {"status": "ok"}


@router.put("/employee-registry")
async def replace_employee_registry_entries(
    payload: EmployeeRegistryReplace,
    user: dict = Depends(get_current_user),
):
    entries = await EmployeeRegistryService().replace_entries(payload.tg_user_ids, created_by=str(user.get("tg_user_id")))
    schedule_aggregation_job()
    return {
        "status": "ok",
        "count": len(entries),
        "entries": [EmployeeRegistryOut.model_validate(entry).model_dump() for entry in entries],
    }
