import csv
import io
from typing import Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from app.api.dependencies import get_db_session
from app.api.report_filters import (
    RawReportParams,
    RawUserFilters,
    ReportFilters,
    get_raw_report_params,
    get_raw_user_filters,
    get_report_filters,
)
from app.services.raw_user_repository import RawUserRepository

# Эндпоинты для таблицы сырых пользователей (RawUsersTable на фронте).

router = APIRouter(tags=["reports-funnel"])

def _normalize_touch_mode(value: str) -> str:
    normalized = (value or "event").strip().lower()
    if normalized in {"first", "first_touch"}:
        return "first"
    if normalized in {"last", "last_touch"}:
        return "last"
    return "event"


@router.get("/funnel-start/raw", summary="Сырые записи пользователей")
# Пагинация (limit/offset), сортировка, touch_mode.
# Для direct_source записей: tg_user_id → None, pokerhub_user_id — из ph_user_id.
async def funnel_raw(
    filters: ReportFilters = Depends(get_report_filters),
    params: RawReportParams = Depends(get_raw_report_params),
    raw_filters: RawUserFilters = Depends(get_raw_user_filters),
    touch_mode: str = Query("event", pattern="^(event|first|last|first_touch|last_touch)$"),
    session=Depends(get_db_session),
) -> dict[str, Any]:
    raw_repo = RawUserRepository()
    normalized_touch_mode = _normalize_touch_mode(touch_mode)
    rows, total = await raw_repo.fetch_raw(
        session, filters, raw_filters, normalized_touch_mode, params.limit, params.offset, params.sort_by, params.sort_direction
    )
    direct_rows = [row for row in rows if row.get("source_category") == "direct_source"]
    for row in direct_rows:
        ph_user_id = row.get("ph_user_id")
        row["pokerhub_user_id"] = str(ph_user_id).strip() if ph_user_id not in (None, "") else None
        row["tg_user_id"] = None

    for row in rows:
        if row.get("source_category") == "direct_source":
            continue
        ph_user_id = row.get("ph_user_id")
        if ph_user_id not in (None, ""):
            row["pokerhub_user_id"] = str(ph_user_id).strip()
    return {"users": rows, "total": total}


@router.get("/funnel-start/export", summary="Экспорт RAW пользователей")
# Стриминговый CSV-ответ (StreamingResponse). Выгружает батчами по 500 строк
# до исчерпания total. Заголовок Content-Disposition: attachment.
async def funnel_export(
    filters: ReportFilters = Depends(get_report_filters),
    params: RawReportParams = Depends(get_raw_report_params),
    raw_filters: RawUserFilters = Depends(get_raw_user_filters),
    touch_mode: str = Query("event", pattern="^(event|first|last|first_touch|last_touch)$"),
    session=Depends(get_db_session),
) -> StreamingResponse:
    raw_repo = RawUserRepository()
    normalized_touch_mode = _normalize_touch_mode(touch_mode)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    header = [
        "id",
        "bot_key",
        "tg_user_id",
        "user_block",
        "created_at",
        "utm_source",
        "utm_campaign",
        "platform_utm_source",
        "platform_utm_campaign",
        "utm_medium",
        "utm_content",
        "utm_term",
        "platform_utm_medium",
        "platform_utm_content",
        "platform_utm_term",
        "advertising_company",
        "budget",
        "converted_to_lead",
        "registered_platform",
        "started_learning",
        "completed_course",
        "used_simulator",
        "interview_reached",
        "interview_passed",
        "offer_received",
        "contract_signed",
        "distance_grinding",
        "channel_subscribed",
        "community_member",
        "team_member",
        "internal_status",
        "learn_start_date",
        "start_course",
        "first_touch_bot",
        "first_touch_campaign",
        "last_touch_bot",
        "last_touch_campaign",
        "source_category",
    ]
    writer.writerow(header)
    batch_size = 500
    offset = 0
    while True:
        rows, total = await raw_repo.fetch_raw(
            session, filters, raw_filters, normalized_touch_mode, batch_size, offset, params.sort_by, params.sort_direction
        )
        if not rows:
            break
        for row in rows:
            writer.writerow([row.get(col, "") for col in header])
        offset += batch_size
        if offset >= total:
            break
    buffer.seek(0)
    response = StreamingResponse(buffer, media_type="text/csv")
    response.headers["Content-Disposition"] = "attachment; filename=raw_users.csv"
    return response
