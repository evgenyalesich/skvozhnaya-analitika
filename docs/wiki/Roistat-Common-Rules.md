# Общие правила и нюансы

Эта страница описывает:

- различия `budget` и `spend` на разных вкладках,
- кэш и TTL,
- нюансы `start_date/end_date` по основным API.

## Budget vs Spend

### Общие источники

- `budget_weekly` — плановый бюджет.
- `ad_metrics_weekly` — фактический расход (`spend`).
- `raw_bot_users.budget` — историческое поле, используется только в Overview и RAW UTM.

### Вкладка Overview и RAW UTM

- Используется `raw_bot_users.budget`.
- Это не фактический `spend` и не перерасчет.
- Вкладки показывают сумму `raw_bot_users.budget`.

### Вкладка RAW Users

- Колонка `Бюджет` вычисляется как бюджет на пользователя.
- Расчет строится из `budget_weekly` и количества `started_learning` по дню/кампании/боту.
- Это не поле `raw_bot_users.budget`.

### Вкладки TotalA / TotalB / TotalC

- Используются данные `GET /api/reports/budgets/weekly`.
- Для формул берется `spend_base`:
- если `spend > 0`, то `spend`.
- иначе `budget`.

### Вкладка Weekly

- Бюджет берется из `budget_weekly`, но если `ad_metrics_weekly.spend > 0`, используется `spend`.

## Кэш и TTL

### ReportCacheService

Кэшируется в Redis (ключи `reports:*`):

- `reports:total`.
- `reports:daily`.
- `reports:breakdown:utm_source`.
- `reports:stages`.
- `reports:summary:{group_by}`.
- `reports:subscriptions_vs_starts:v2:*`.

TTL:

- `settings.cache_ttl_seconds`.

Условие кэша:

- Кэш используется только если фильтры не заданы (`ReportFilters.has_filters() == false`).

### Roistat Weekly

- Ключ: `reports:roistat_weekly:v2:{mode}:{event_start}:{event_end}:{first_touch_start}:{first_touch_end}`.
- TTL: `settings.weekly_cache_ttl_seconds`.

### Weekly по ботам/РК (TotalA/TotalB)

- Используется `WeeklyReportCache`.
- Данные берутся из Redis ключей `reports:weekly:{group}:{group_key}:{month}`.
- Эти ключи формируются внешними задачами и не пересчитываются по требованию.

### Статусы синков

- Ключи `sync:last_*` в Redis.
- Обновляются воркерами при выполнении задач.

## Нюансы start_date / end_date

### Общие фильтры (ReportFilters)

- `start_date` и `end_date` применяются к `raw_bot_users.created_at`.
- `end_date` включительный: добавляется 1 день на бэке.
- Максимальный диапазон: 730 дней.

### Funnel / Overview / RAW

- `GET /api/reports/funnel-start/*` используют `ReportFilters`.
- Дата — `created_at`.

### TG SUBS

- `GET /api/reports/subscriptions/compare` использует отдельные параметры `start_date` и `end_date`.
- Если оба не заданы, берется дефолтный диапазон `settings.subscriptions_compare_default_days`.
- Дата — поле `agg_tg_subs_daily.day`.

### Weekly (Roistat)

- Параметры:
- `event_start`, `event_end` для фильтрации дат событий в Google Sheets.
- `first_touch_start`, `first_touch_end` для отбора когорты.
- Если `mode=first_touch` и `first_touch_*` не переданы, они будут взяты из `event_start/event_end`.

### Touch (TotalC)

- `GET /api/reports/touch/funnel-summary`:
- `first` использует `created_at`.
- `last` использует `learn_start_date`.
- Фильтры применяются к соответствующей дате.

### Budgets Weekly

- `GET /api/reports/budgets/weekly` использует `start_date` и `end_date`.
- При `interval=day` сравнивает по `period_start` (день).
- При `interval=week` сравнивает по `period_start` (неделя).
