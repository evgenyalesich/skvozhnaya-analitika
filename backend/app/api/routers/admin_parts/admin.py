"""Фасад admin-роутера. Все эндпоинты /api/admin/* требуют get_current_user (JWT).
Логика разбита по слоям: admin_sync, admin_marketing, admin_access.
"""

from app.api.routers.admin_parts.admin_impl import *  # noqa: F401,F403
