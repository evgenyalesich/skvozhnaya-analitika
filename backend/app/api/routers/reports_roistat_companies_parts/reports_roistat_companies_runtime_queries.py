# Фасад для трёх SQL-построителей Roistat companies:
#   build_main_query       — основной отчёт (weekly или cohort) по company
#   build_bot_query        — тот же отчёт с детализацией до bot_key
#   build_week_totals_query — итоговые суммы по неделям (только в weekly mode)

from app.api.routers.reports_roistat_companies_runtime_query_bot import build_bot_query
from app.api.routers.reports_roistat_companies_runtime_query_main import build_main_query
from app.api.routers.reports_roistat_companies_runtime_query_week_totals import (
    build_week_totals_query,
)

__all__ = ["build_main_query", "build_week_totals_query", "build_bot_query"]
