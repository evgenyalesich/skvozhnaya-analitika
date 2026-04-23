# Кэш и обновления

Эта страница описывает кэширование, TTL и ручные обновления по всем основным ручкам.

## Общие правила

- Кэш хранится в Redis.
- Базовый TTL берется из `settings.cache_ttl_seconds`.
- Кэш используется только когда фильтры не заданы (`ReportFilters.has_filters() == false`).

## ReportCacheService

Файл:

- `backend/app/services/report_cache_service.py`.

Ключи и условия:

- `reports:total`.
- `GET /api/reports/funnel-start/total`.
- Кэш только без фильтров.

- `reports:daily`.
- `GET /api/reports/funnel-start/daily`.
- Кэш только без фильтров.

- `reports:breakdown:utm_source`.
- `GET /api/reports/funnel-start/breakdown` при `group_by=utm_source`.
- Кэш только без фильтров.

- `reports:stages`.
- `GET /api/reports/funnel-start/stages`.
- Кэш только без фильтров.

- `reports:summary:{group_by}`.
- `GET /api/reports/funnel-start/summary`.
- Кэш только без фильтров.

- `reports:subscriptions_vs_starts:v2:{fingerprint}`.
- `GET /api/reports/subscriptions/compare`.
- Кэшируется всегда, но при пустом результате возвращается последний `last_good`.

TTL:

- `settings.cache_ttl_seconds` для всех ключей выше.

## Roistat Weekly

Файл:

- `backend/app/api/routers/reports.py`.

Ключ:

- `reports:roistat_weekly:v2:{mode}:{event_start}:{event_end}:{first_touch_start}:{first_touch_end}`.

TTL:

- `settings.weekly_cache_ttl_seconds`.

Обновление:

- Прямой пересчет по `GET /api/reports/roistat-weekly`.
- Очистка кэша: `redis-cli --scan --pattern 'reports:roistat_weekly:v2:*' | xargs -r redis-cli del`.

## Weekly по ботам и РК

Файл:

- `backend/app/services/weekly_reports.py`.

Ключи:

- `reports:weekly:{group}:{group_key}:months`.
- `reports:weekly:{group}:{group_key}:{month}`.

TTL:

- TTL задается при записи кэша внешними задачами.
- В UI используются только значения из Redis, пересчета по запросу нет.

## Статусы синков

Файл:

- `backend/app/api/routers/admin.py`.

Ключи:

- `sync:last_ingestion`.
- `sync:last_ingestion_success`.
- `sync:last_sm`.
- `sync:last_roistat_weekly`.
- `sync:last_roistat_weekly_success`.

TTL:

- TTL выставляют воркеры.

## Ручные обновления

Ручки:

- `POST /api/admin/sync-all`.
- `POST /api/admin/sync-google-sheets`.
- `POST /api/admin/sync-roistat-weekly`.
- `POST /api/advertising-companies/rebuild`.

Примечания:

- Для ручек `admin` нужен `Authorization: Bearer <token>`.
- Кнопки UI вызывают эти ручки из `SystemSettingsDialog`.
