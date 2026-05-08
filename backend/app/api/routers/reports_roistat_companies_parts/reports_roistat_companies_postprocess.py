# Постобработка результатов Roistat companies: сборка финального payload.
# Порядок: build_payload_rows (serialize DB rows) → apply_lesson_registration_metrics (PH Lessons)
# → apply_cohort_stage_override (только для cohort mode) → кеш.

from typing import Any

from app.api.routers.reports_roistat_companies_postprocess_cohort import (
    apply_cohort_stage_override,
)
from app.api.routers.reports_roistat_companies_postprocess_lessons import (
    apply_lesson_registration_metrics,
)
from app.api.routers.reports_roistat_companies_postprocess_shared import (
    build_payload_rows,
)


async def build_roistat_companies_payload(
    *,
    session,
    sa_text,
    params,
    db_rows,
    db_bot_rows,
    db_week_totals_rows,
    normalized_company_sql: str,
    source_touch_filter_sql: str,
    display_mode: str,
    cohort_cte: str,
    cohort_join: str,
    utm_filter_sql: str,
    cache,
    cache_key: str,
    stale_key: str,
    settings,
):
    rows_payload, bot_rows_payload, week_totals_payload = build_payload_rows(
        db_rows=db_rows,
        db_bot_rows=db_bot_rows,
        db_week_totals_rows=db_week_totals_rows,
    )

    await apply_lesson_registration_metrics(
        session=session,
        sa_text=sa_text,
        params=params,
        cohort_cte=cohort_cte,
        cohort_join=cohort_join,
        normalized_company_sql=normalized_company_sql,
        source_touch_filter_sql=source_touch_filter_sql,
        rows_payload=rows_payload,
        bot_rows_payload=bot_rows_payload,
        week_totals_payload=week_totals_payload,
        display_mode=display_mode,
    )

    if display_mode == "cohort":
        await apply_cohort_stage_override(
            session=session,
            sa_text=sa_text,
            params=params,
            cohort_cte=cohort_cte,
            cohort_join=cohort_join,
            utm_filter_sql=utm_filter_sql,
            normalized_company_sql=normalized_company_sql,
            source_touch_filter_sql=source_touch_filter_sql,
            rows_payload=rows_payload,
            bot_rows_payload=bot_rows_payload,
            week_totals_payload=week_totals_payload,
        )
        rows_payload.sort(key=lambda row: (row["week_start"], row["company"]), reverse=True)
        bot_rows_payload.sort(key=lambda row: (row["week_start"], row["company"], row["bot_key"]), reverse=True)

    payload: dict[str, Any] = {
        "rows": rows_payload,
        "bot_rows": bot_rows_payload,
        "week_totals": week_totals_payload,
    }
    primary_ttl = settings.weekly_cache_ttl_seconds
    stale_ttl = max(primary_ttl * 7, 7 * 24 * 60 * 60)
    await cache.set_json(cache_key, payload, ttl=primary_ttl)
    await cache.set_json(stale_key, payload, ttl=stale_ttl)
    return payload
