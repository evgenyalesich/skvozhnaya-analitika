from sqlalchemy.ext.asyncio import AsyncSession

from app.api.report_filters import RawUserFilters, ReportFilters
from app.services.raw_user_repository_fetch import RawUserRepositoryFetchMixin
from app.services.raw_user_repository_filters import RawUserRepositoryFiltersMixin
from app.services.raw_user_repository_helpers import RawUserRepositoryHelpersMixin


class RawUserRepository(
    RawUserRepositoryHelpersMixin,
    RawUserRepositoryFiltersMixin,
    RawUserRepositoryFetchMixin,
):
    """Репозиторий для работы с raw_bot_users (таблица сырых данных пользователей).

    Слои:
    - Fetch    — fetch_raw() + _serialize(): выборка с пагинацией и обогащением
    - Filters  — _apply_filters() / _apply_raw_filters(): применение всех фильтров
    - Helpers  — вспомогательные методы (загрузка зеркала, budget_cpa_map, first_seen_maps)
    """


__all__ = ["RawUserRepository", "ReportFilters", "RawUserFilters", "AsyncSession"]
