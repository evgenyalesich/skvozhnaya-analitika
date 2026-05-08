from datetime import date
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import get_db_session
from app.api.report_filters import get_report_filters
from app.schemas.reports import RoistatLessonsReportResponse, RoistatWeeklyReportResponse

from . import reports_roistat_logic as roistat_logic

# HTTP-слой Roistat-отчётов. Вся логика в reports_roistat_logic.py — здесь только
# парсинг параметров и передача в logic-функции.

router = APIRouter(tags=["reports-roistat"])


# ===== Roistat HTTP layer =====

@router.get("/roistat-weekly/companies-weekly", summary="Основной отчёт: Месяц → Неделя → РК")
# Самый тяжёлый эндпоинт — иерархия месяц→неделя→компания с полной воронкой.
# mode: event|first_touch|last_touch — режим когорты.
# display_mode: weekly|cohort — как группировать данные на фронте.
async def roistat_weekly_by_company(
    event_start: Optional[date] = Query(None),
    event_end: Optional[date] = Query(None),
    mode: str = Query("event", pattern="^(event|first_touch|last_touch)$"),
    first_touch_start: Optional[date] = Query(None),
    first_touch_end: Optional[date] = Query(None),
    display_mode: str = Query("weekly", pattern="^(weekly|cohort)$"),
    bots: Optional[List[str]] = Query(None),
    advertising_companies: Optional[List[str]] = Query(None),
    utm_source: Optional[List[str]] = Query(None),
    utm_campaign: Optional[List[str]] = Query(None),
    utm_medium: Optional[List[str]] = Query(None),
    utm_content: Optional[List[str]] = Query(None),
    utm_term: Optional[List[str]] = Query(None),
    session=Depends(get_db_session),
) -> dict[str, Any]:
    return await roistat_logic.roistat_weekly_by_company(
        event_start=event_start,
        event_end=event_end,
        mode=mode,
        first_touch_start=first_touch_start,
        first_touch_end=first_touch_end,
        display_mode=display_mode,
        bots=bots,
        advertising_companies=advertising_companies,
        utm_source=utm_source,
        utm_campaign=utm_campaign,
        utm_medium=utm_medium,
        utm_content=utm_content,
        utm_term=utm_term,
        session=session,
    )


# ===== Tree view =====
@router.get("/roistat-weekly/tree", summary="Дерево Roistat Weekly: платформа → кабинет → бот")
async def roistat_weekly_tree(
    event_start: Optional[date] = Query(None),
    event_end: Optional[date] = Query(None),
    session=Depends(get_db_session),
) -> dict[str, Any]:
    return await roistat_logic.roistat_weekly_tree(
        event_start=event_start,
        event_end=event_end,
        session=session,
    )


# ===== Weekly response =====
@router.get("/roistat-weekly", summary="Weekly для Roistat", response_model=RoistatWeeklyReportResponse)
async def roistat_weekly(
    event_start: Optional[date] = Query(None),
    event_end: Optional[date] = Query(None),
    mode: str = Query("event", pattern="^(event|first_touch|last_touch)$"),
    first_touch_start: Optional[date] = Query(None),
    first_touch_end: Optional[date] = Query(None),
    bots: Optional[List[str]] = Query(None),
    session=Depends(get_db_session),
) -> RoistatWeeklyReportResponse:
    return await roistat_logic.roistat_weekly(
        event_start=event_start,
        event_end=event_end,
        mode=mode,
        first_touch_start=first_touch_start,
        first_touch_end=first_touch_end,
        bots=bots,
        session=session,
    )


# ===== Lessons matrix =====
@router.get("/roistat-lessons", summary="Матрица уроков PokerHub для Roistat", response_model=RoistatLessonsReportResponse)
# Показывает прогресс по урокам из PhUserMirrorReplica для пользователей
# с фильтрацией по pokerhub_user_id и диапазону learn_start_date.
async def roistat_lessons(
    filters=Depends(get_report_filters),
    pokerhub_user_id: Optional[str] = Query(None),
    learn_start_date_from: Optional[date] = Query(None),
    learn_start_date_to: Optional[date] = Query(None),
    session=Depends(get_db_session),
) -> RoistatLessonsReportResponse:
    return await roistat_logic.roistat_lessons(
        filters=filters,
        pokerhub_user_id=pokerhub_user_id,
        learn_start_date_from=learn_start_date_from,
        learn_start_date_to=learn_start_date_to,
        session=session,
    )
