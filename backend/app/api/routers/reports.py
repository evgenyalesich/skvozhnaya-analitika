from fastapi import APIRouter, Depends, HTTPException, Query
from datetime import date, timedelta

from app.api.dependencies import get_db_session
from app.api.report_filters import ReportFilters, get_report_filters
from app.schemas.reports import WeeklyReportResponse
from app.services.weekly_reports import WeeklyReportCache
from app.api.routers.reports_roistat_companies_parts.reports_roistat_companies_runtime_core import (
    roistat_weekly_by_company,
)
from . import reports_extras
from . import reports_funnel
from . import reports_roistat

router = APIRouter(prefix="/api/reports", tags=["reports"])
weekly_cache = WeeklyReportCache()
router.include_router(reports_extras.router)
router.include_router(reports_funnel.router)
router.include_router(reports_roistat.router)

# ===== Weekly reports =====

@router.get("/weekly", summary="Понедельная статистика", response_model=WeeklyReportResponse)
# Читает из Redis-кеша (ключ reports:weekly:{bot|company}:{key}:{YYYY-MM}).
# Данные прогреваются aggregate_refresher после пересчёта агрегатов.
async def weekly_stats(
    group_by: str = Query("bot", pattern="^(bot|company)$"),
    group_key: str | None = Query(None, alias="group_key"),
):
    if not group_key:
        raise HTTPException(status_code=400, detail="group_key is required")
    months = await weekly_cache.list_months(group_by, group_key)
    data = {}
    for month in months:
        data[month] = await weekly_cache.fetch_weekly(group_by, group_key, month)
    return WeeklyReportResponse(group_key=group_key, months=data)


@router.get("/weekly-filtered", summary="Понедельная статистика с UTM-фильтрами", response_model=WeeklyReportResponse)
# Если UTM-фильтры не заданы — отдаёт кеш (как /weekly).
# При активных фильтрах — динамический SQL напрямую в БД (CTE с first_seen и ph_reg_by_week).
async def weekly_stats_filtered(
    group_by: str = Query("bot", pattern="^(bot|company)$"),
    group_key: str | None = Query(None),
    filters: ReportFilters = Depends(get_report_filters),
    session=Depends(get_db_session),
):
    if not group_key:
        raise HTTPException(status_code=400, detail="group_key is required")

    from collections import defaultdict

    payload = await roistat_weekly_by_company(
        event_start=filters.start_date,
        event_end=filters.end_date,
        mode="event",
        first_touch_start=None,
        first_touch_end=None,
        display_mode="weekly",
        bots=filters.bots or None,
        advertising_companies=filters.advertising_companies or None,
        utm_source=filters.utm_source or None,
        utm_campaign=filters.utm_campaign or None,
        utm_medium=filters.utm_medium or None,
        utm_content=filters.utm_content or None,
        utm_term=filters.utm_term or None,
        session=session,
    )

    source_rows = payload.get("bot_rows" if group_by == "bot" else "rows", [])
    weekly_totals: dict[str, dict[str, int]] = {}
    for row in source_rows:
        row_key = str(row.get("bot_key") if group_by == "bot" else row.get("company") or "")
        if row_key != group_key:
            continue
        week_start = str(row.get("week_start") or "")
        if not week_start:
            continue
        current = weekly_totals.setdefault(
            week_start,
            {
                "entered": 0,
                "new_in_system": 0,
                "old_in_system": 0,
                "lead": 0,
                "platform": 0,
                "learning": 0,
                "course": 0,
                "interview": 0,
                "passed": 0,
                "offer": 0,
                "contract": 0,
                "distance_grinding": 0,
            },
        )
        current["entered"] += int(row.get("entered_all") or 0)
        current["new_in_system"] += int(row.get("new_in_system") or 0)
        current["old_in_system"] += int(row.get("old_in_system") or 0)
        current["lead"] += int(row.get("almanah_starts") or 0) + int(row.get("direct_source_cnt") or 0)
        current["platform"] += int(row.get("platform_cnt") or 0)
        current["learning"] += int(row.get("started_learning") or 0)
        current["course"] += int(row.get("completed_course") or 0)
        current["interview"] += int(row.get("interview_reached") or 0)
        current["offer"] += int(row.get("offer_received") or 0)
        current["contract"] += int(row.get("contract_signed") or 0)
        current["distance_grinding"] += int(row.get("distance_grinding") or 0)

    monthly: dict[str, list[dict]] = defaultdict(list)
    for week_start in sorted(weekly_totals.keys()):
        values = weekly_totals[week_start]
        month_key = week_start[:7]
        parsed_ws = date.fromisoformat(week_start)
        week_end = (parsed_ws + timedelta(days=6)).isoformat()
        monthly[month_key].append(
            {
                "week_start": week_start,
                "week_end": week_end,
                "values": values,
            }
        )

    return WeeklyReportResponse(group_key=group_key, months=dict(monthly))
