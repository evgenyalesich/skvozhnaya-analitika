# Роутер build_bot_query: выбирает между weekly и cohort вариантом bot-уровневого SQL-запроса.

from collections.abc import Callable
from typing import Any

from app.api.routers.reports_roistat_companies_runtime_query_bot_cohort import (
    build_bot_cohort_query,
)
from app.api.routers.reports_roistat_companies_runtime_query_bot_weekly import (
    build_bot_weekly_query,
)


def build_bot_query(
    *,
    sa_text: Callable[[str], Any],
    display_mode: str,
    cohort_cte: str,
    cohort_join: str,
    event_date_filter: str,
    cohort_all_starts_join: str,
    utm_filter_sql: str,
    normalized_company_sql: str,
    source_touch_filter_sql: str,
    budget_filter_sql: str,
    lc_company_sql: str,
) -> Any:
    if display_mode == "weekly":
        return build_bot_weekly_query(
            sa_text=sa_text,
            cohort_cte=cohort_cte,
            cohort_join=cohort_join,
            event_date_filter=event_date_filter,
            utm_filter_sql=utm_filter_sql,
            normalized_company_sql=normalized_company_sql,
            source_touch_filter_sql=source_touch_filter_sql,
            budget_filter_sql=budget_filter_sql,
            lc_company_sql=lc_company_sql,
        )

    return build_bot_cohort_query(
        sa_text=sa_text,
        cohort_cte=cohort_cte,
        cohort_join=cohort_join,
        event_date_filter=event_date_filter,
        cohort_all_starts_join=cohort_all_starts_join,
        utm_filter_sql=utm_filter_sql,
        normalized_company_sql=normalized_company_sql,
        source_touch_filter_sql=source_touch_filter_sql,
        budget_filter_sql=budget_filter_sql,
    )
