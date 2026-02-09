# Карта файлов Roistat (что за что отвечает)

Ниже перечислена "поверхность" Roistat в репозитории: UI, API, расчет, экспорт, а также зависимости.

## Фронтенд

`frontend/src/pages/OverviewPage.tsx`

- Хостит таб `WEEKLY`.
- Держит состояние UI:
  - `weeklyUseFirstTouch` (тумблер)
  - `weeklyMonth` (выбранный месяц)
- Считает `weeklyMonthRange` как fallback для `first_touch_start/end`.
- Вызывает `useRoistatWeekly(...)` и передает данные в `WeeklyTable`.

`frontend/src/hooks/useRoistatWeekly.ts`

- Хук запроса `GET /api/reports/roistat-weekly`.
- Собирает query params:
  - `mode`
  - `event_start/event_end`
  - `first_touch_start/first_touch_end`
- Возвращает `{ rows, loading, error, refresh }`.

`frontend/src/components/WeeklyTable.tsx`

- Рендерит таблицу и группировку по месяцам.
- CR% колонки считает на клиенте из числовых полей.
- Выбор месяца сделан контролируемым (родитель может управлять), чтобы выбранный месяц мог влиять на параметры запроса.

`frontend/src/hooks/useTelegramAuth.ts`

- Стартует Telegram login и поллит статус.
- Сохраняет `auth_token` в localStorage и выставляет axios Authorization header.

## Бекенд

`backend/app/api/routers/reports.py`

- `GET /api/reports/roistat-weekly`:
  - парсит query params
  - поддерживает backward-compat поведение
  - кеширует в Redis под `reports:roistat_weekly:v2:*`
  - вызывает `RoistatWeeklyReport().build_weekly_rows(...)`

`backend/app/schemas/reports.py`

- Pydantic модели ответа:
  - `RoistatWeeklyRow`
  - `RoistatWeeklyReportResponse`

`backend/app/services/roistat_weekly_report.py`

- Основная логика расчета `Weekly`.
- Читает Google Sheets (`'pokerhub_robot'!A:U`).
- Применяет:
  - бакетинг по неделям месяца (1, 8, 15, 22, 29)
  - фильтр по датам событий (`event_start/event_end`)
  - cohort-фильтр по `tg_user_id` (`mode=first_touch`)
- Обогащает:
  - `budget` из Postgres (`budget_weekly`, `ad_metrics_weekly`)
  - `saloon` из Postgres:
    - `agg_tg_subs_daily` без когорты
    - `telegram_subscription_events` в режиме когорты
- Делает экспорт в Google Sheets (`export_to_sheet`).

`backend/app/worker/tasks.py`

- RQ задачи.
- Roistat export:
  - `schedule_roistat_weekly_export_job()`
  - `run_roistat_weekly_export_job()`
- Пишет статусы:
  - `sync:last_roistat_weekly`
  - `sync:last_roistat_weekly_success`

`backend/app/api/routers/admin.py`

- Admin endpoint:
  - `POST /api/admin/sync-roistat-weekly`
- `GET /api/admin/sync-status` включает статусы roistat weekly.

`backend/app/services/aggregate_refresher.py`

- Пересобирает агрегаты по дням из сырых таблиц.
- Заполняет `agg_tg_subs_daily`, включая `saloon_subscribed/saloon_unsubscribed` на основе `TELEGRAM_COMMUNITY_ID`.

`backend/app/models/analytics.py`

- ORM модели:
  - `TgSubsDailyAgg` (`agg_tg_subs_daily`)
  - `TelegramSubscriptionEvent` (`telegram_subscription_events`)

`backend/app/core/config.py`

- Настройки, связанные с Roistat:
  - `google_sheets_credentials_path`
  - `google_sheets_spreadsheet_id`
  - `roistat_weekly_sheet_id`
  - `roistat_weekly_sheet_title`
  - `weekly_cache_ttl_seconds`

`backend/app/services/telegram_auth.py` и `backend/app/api/routers/auth.py`

- Telegram-аутентификация для доступа к дашборду.
