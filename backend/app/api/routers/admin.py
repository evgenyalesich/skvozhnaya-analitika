from typing import List
from datetime import date

from fastapi import APIRouter, Depends, HTTPException

from app.api.dependencies import get_access_service, get_current_user, get_db_session
from app.db.postgres_explorer import PostgresExplorer
from app.schemas.db_explorer import DatabaseListResponse, DatabaseQueryRequest, DatabaseQueryResponse
from app.schemas.telegram_access import TelegramAccessCreate, TelegramAccessOut
from app.services.telegram_access_service import TelegramAccessService
from app.services.system_settings_service import SystemSettingsService
from app.schemas.system_settings import SystemSettingsOut, SystemSettingsUpdate, SyncEventLogOut
from app.worker.tasks import (
    queue,
    schedule_aggregation_job,
    schedule_google_sheets_job,
    schedule_ingestion_job,
    schedule_roistat_weekly_export_job,
    schedule_telegram_job,
)
from app.core.redis_client import RedisCache

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.post("/ingest")
def trigger_ingest():
    schedule_ingestion_job()
    return {"status": "ok", "message": "Ingestion job queued"}


@router.post("/sync-pokerhub")
def sync_pokerhub():
    schedule_ingestion_job()
    return {"status": "ok", "source": "pokerhub", "message": "Синхронизация PokerHub запущена"}


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
def sync_all():
    schedule_ingestion_job()
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
