from typing import Optional

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import get_db_session
from app.services.raw_user_repository import RawUserRepository
from app.services.report_cache_service import ReportCacheService

router = APIRouter(prefix="/api/reports", tags=["reports"])
report_cache = ReportCacheService()


@router.get("/funnel-start/total", summary="Общее количество пользователей и бюджет")
async def funnel_total(session=Depends(get_db_session)) -> dict[str, Optional[float]]:
    return await report_cache.total(session)


@router.get("/funnel-start/daily", summary="Дневная динамика")
async def funnel_daily(
    limit: int = Query(30, ge=1, le=90), session=Depends(get_db_session)
) -> dict[str, list[dict[str, Optional[float]]]]:
    data = await report_cache.daily(session, limit)
    return {"data": data}


@router.get("/funnel-start/breakdown", summary="Разбивка пользователей")
async def funnel_breakdown(
    group_by: str = Query("utm_source", pattern="^(utm_source|utm_campaign|advertising_company)$"),
    limit: int = Query(20, ge=1, le=50),
    session=Depends(get_db_session),
) -> dict[str, list[dict[str, Optional[float]]]]:
    data = await report_cache.breakdown(session, group_by, limit)
    return {"breakdown": data}


@router.get("/funnel-start/raw", summary="Сырые записи пользователей")
async def funnel_raw(
    limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0), session=Depends(get_db_session)
) -> dict[str, list[dict[str, Optional[str]]]]:
    raw_repo = RawUserRepository()
    data = await raw_repo.fetch_raw(session, limit, offset)
    return {"users": data}
