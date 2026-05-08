"""Фасад: собирает router из reports_funnel_runtime + reports_funnel_raw.
Все эндпоинты: /api/reports/funnel-start/*.
"""

from app.api.routers.reports_funnel_parts.reports_funnel_impl import *  # noqa: F401,F403
