# Паттерн по всему проекту: крупные сервисы разбиты на Mixin-слои по задачам,
# а финальный класс просто собирает их через множественное наследование.
# Здесь: Rebuild — пересчёт агрегатов в БД, Cache — прогрев Redis после пересчёта.

from app.services.aggregate_refresher_cache import AggregateRefresherCacheMixin
from app.services.aggregate_refresher_rebuild import AggregateRefresherRebuildMixin


class AggregateRefresher(AggregateRefresherRebuildMixin, AggregateRefresherCacheMixin):
    """Пересчитывает агрегатные таблицы (agg_daily_new_users, agg_weekly_funnel_*,
    agg_tg_subs_daily) и прогревает Redis-кеш для основных отчётов.

    Вызывается из worker-задачи после ингестии или принудительно через admin API.
    Точка входа: метод refresh(days=N).
    """
