# Отчёт по урокам PokerHub (Roistat Lessons).
# Строит матрицу: строка = пользователь (tg/ph), колонки = отдельные уроки курса.
# Кеш: ключ по всем ReportFilters + learn_start_date + pokerhub_user_id, TTL 300 с.
# Делегирует в RoistatLessonsReport.build().

from datetime import date
import json
from typing import Optional

from fastapi import Depends, HTTPException, Query

from app.api.dependencies import get_db_session
from app.api.report_filters import ReportFilters, get_report_filters
from app.core.redis_client import RedisCache
from app.schemas.reports import (
    RoistatLessonColumn,
    RoistatLessonCourse,
    RoistatLessonsReportResponse,
    RoistatLessonUserRow,
)
from app.services.roistat_lessons_report import RoistatLessonsReport


# ===== Roistat lessons logic =====
async def roistat_lessons(
    filters: ReportFilters = Depends(get_report_filters),
    pokerhub_user_id: Optional[str] = Query(None),
    learn_start_date_from: Optional[date] = Query(None),
    learn_start_date_to: Optional[date] = Query(None),
    session=Depends(get_db_session),
):
    effective_learn_start_from = learn_start_date_from
    effective_learn_start_to = learn_start_date_to
    if effective_learn_start_from and effective_learn_start_to and effective_learn_start_to < effective_learn_start_from:
        raise HTTPException(status_code=400, detail="learn_start_date_to must be after learn_start_date_from")

    cache = RedisCache()
    cache_key = "reports:roistat_lessons:" + json.dumps(
        {
            "cache_v": 5,
            "start_date": filters.start_date.isoformat() if filters.start_date else None,
            "end_date": filters.end_date.isoformat() if filters.end_date else None,
            "learn_start_date_from": effective_learn_start_from.isoformat() if effective_learn_start_from else None,
            "learn_start_date_to": effective_learn_start_to.isoformat() if effective_learn_start_to else None,
            "bots": filters.bots,
            "advertising_companies": filters.advertising_companies,
            "utm_source": filters.utm_source,
            "utm_campaign": filters.utm_campaign,
            "utm_medium": filters.utm_medium,
            "utm_content": filters.utm_content,
            "utm_term": filters.utm_term,
            "user_scope": filters.user_scope,
            "pokerhub_user_id": pokerhub_user_id,
        },
        sort_keys=True,
    )
    cached = await cache.get_json(cache_key)
    if cached is not None:
        return RoistatLessonsReportResponse(**cached)

    courses = await RoistatLessonsReport().build(
        session,
        filters,
        pokerhub_user_id=pokerhub_user_id,
        learn_start_date_from=effective_learn_start_from,
        learn_start_date_to=effective_learn_start_to,
    )
    response = RoistatLessonsReportResponse(
        courses=[
            RoistatLessonCourse(
                course=course.course,
                total_lessons=course.total_lessons,
                columns=[
                    RoistatLessonColumn(
                        key=column.key,
                        label=column.label,
                        module=column.module,
                        lesson=column.lesson,
                    )
                    for column in course.columns
                ],
                rows=[
                    RoistatLessonUserRow(
                        tg_user_id=row.tg_user_id,
                        username=row.username,
                        pokerhub_user_id=row.pokerhub_user_id,
                        completed_lessons=row.completed_lessons,
                        lessons=row.lessons,
                    )
                    for row in course.rows
                ],
            )
            for course in courses
        ]
    )
    await cache.set_json(cache_key, response.model_dump(), ttl=300)
    return response
