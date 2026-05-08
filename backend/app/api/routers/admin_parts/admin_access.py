from typing import List

import asyncpg
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text

from app.api.dependencies import get_access_service, get_current_user, get_db_session
from app.core.config import settings
from app.core.redis_client import RedisCache
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
from app.worker.tasks import schedule_aggregation_job

# Управление доступом пользователей, реестром сотрудников, UTM-покрытием и репликацией.
# Требует авторизации (get_current_user из зависимостей admin_runtime).

router = APIRouter()


@router.get("/databases", response_model=DatabaseListResponse)
# Список всех PostgreSQL-баз в кластере (через PostgresExplorer).
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
# CRUD белого списка Telegram-пользователей (telegram_access таблица).
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
async def add_employee_registry_entry(payload: EmployeeRegistryCreate, user: dict = Depends(get_current_user)):
    entry = await EmployeeRegistryService().add_entry(payload.tg_user_id, created_by=str(user.get("tg_user_id")))
    schedule_aggregation_job()
    return EmployeeRegistryOut.model_validate(entry)


@router.post("/employee-registry/bulk")
async def add_employee_registry_entries(payload: EmployeeRegistryBulkCreate, user: dict = Depends(get_current_user)):
    entries = await EmployeeRegistryService().add_entries(payload.tg_user_ids, created_by=str(user.get("tg_user_id")))
    if entries:
        schedule_aggregation_job()
    return {
        "status": "ok",
        "added": len(entries),
        "entries": [EmployeeRegistryOut.model_validate(entry).model_dump() for entry in entries],
    }


@router.delete("/employee-registry/{tg_user_id}")
async def remove_employee_registry_entry(tg_user_id: int, _user: dict = Depends(get_current_user)):
    await EmployeeRegistryService().remove_entry(tg_user_id)
    schedule_aggregation_job()
    return {"status": "ok"}


@router.put("/employee-registry")
async def replace_employee_registry_entries(payload: EmployeeRegistryReplace, user: dict = Depends(get_current_user)):
    entries = await EmployeeRegistryService().replace_entries(payload.tg_user_ids, created_by=str(user.get("tg_user_id")))
    schedule_aggregation_job()
    return {
        "status": "ok",
        "count": len(entries),
        "entries": [EmployeeRegistryOut.model_validate(entry).model_dump() for entry in entries],
    }


@router.get("/utm-coverage")
# Показывает все уникальные UTM source+campaign комбинации с числом пользователей.
# Помечает комбинации, появившиеся за последние 7 дней (is_new=True).
async def utm_coverage(session=Depends(get_db_session)):
    result = await session.execute(text("""
        WITH utm_data AS (
            SELECT
                COALESCE(platform_utm_source, utm_source) AS source,
                COALESCE(platform_utm_campaign, utm_campaign) AS campaign,
                COUNT(*) AS total_users,
                COUNT(*) FILTER (WHERE created_at >= NOW() - INTERVAL '7 days') AS new_7d,
                COUNT(*) FILTER (WHERE created_at >= NOW() - INTERVAL '1 day') AS new_1d,
                MIN(created_at) AS first_seen,
                MAX(created_at) AS last_seen
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
        "new_last_7d": sum(1 for item in labels if item["is_new"]),
        "labels": labels,
    }


@router.post("/utm-cache-clear")
async def utm_cache_clear():
    cache = RedisCache()
    await cache.delete_pattern("utm:options:*")
    return {"status": "ok"}


@router.get("/replication/metrics")
# Читает метрики всех replication streams из Redis (ключи replication:stream:*:metrics).
async def replication_metrics():
    cache = RedisCache()
    streams = await cache.get_json_by_pattern("replication:stream:*:metrics", limit=500)
    return {"streams": list(streams.values()), "total_streams": len(streams)}


@router.get("/replication/slots")
# Читает pg_replication_slots напрямую через asyncpg (postgres_admin_dsn).
# Показывает retained WAL в human-readable формате — важно следить, чтобы не рос.
async def replication_slots():
    dsn = str(settings.postgres_admin_dsn).replace("postgresql+asyncpg://", "postgresql://")
    conn = await asyncpg.connect(dsn)
    try:
        rows = await conn.fetch(
            """
            SELECT
                slot_name,
                database,
                active,
                restart_lsn,
                confirmed_flush_lsn,
                pg_size_pretty(pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn)) AS retained_wal,
                pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn)::bigint AS retained_wal_bytes
            FROM pg_replication_slots
            ORDER BY retained_wal_bytes DESC NULLS LAST, slot_name
            """
        )
    finally:
        await conn.close()
    return {"slots": [dict(row) for row in rows]}


@router.get("/replication/dlq")
# Dead Letter Queue репликации: последние N застрявших событий с reason + error.
async def replication_dlq(limit: int = 100, session=Depends(get_db_session)):
    limit = max(1, min(limit, 1000))
    result = await session.execute(
        text(
            """
            SELECT id, db_name, bot_key, reason, payload, error, created_at
            FROM replication_dlq
            ORDER BY created_at DESC
            LIMIT :limit
            """
        ),
        {"limit": limit},
    )
    rows = result.fetchall()
    return {"items": [dict(row._mapping) for row in rows], "count": len(rows)}
