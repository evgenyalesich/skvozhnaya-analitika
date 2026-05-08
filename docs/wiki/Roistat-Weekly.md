# Roistat Weekly

## Что это за экран

`Weekly` — недельный отчёт по движению cohort через основные этапы:

- lead / almanah starts;
- new/old in system;
- platform;
- learning;
- started learning;
- course mix (`base`, `mtt`, `spin`, `cash`);
- not started;
- channel/saloon subscriptions;
- completed course / contract;
- budget.

## Точки входа

Frontend:

- `frontend/src/components/layout/OverviewPage.tsx`
- `frontend/src/hooks/useRoistatWeekly.ts`
- `frontend/src/components/WeeklyTable.tsx`

Backend:

- `backend/app/api/routers/reports_roistat.py`
- `backend/app/api/routers/reports_roistat_weekly.py`
- `backend/app/services/roistat_weekly_parts/*`

## API-контракт

Endpoint:

- `GET /api/reports/roistat-weekly`

Параметры:

- `mode`: `event | first_touch | last_touch`
- `event_start`, `event_end`
- `first_touch_start`, `first_touch_end`
- `bots[]`

Смысл режимов:

- `event` — без cohort-фильтра по touch-датам, метрики считаются по датам событий;
- `first_touch` — сначала строится cohort по первому касанию, затем считаются недельные события только для этой когорты;
- `last_touch` — аналогично, но cohort строится по последнему касанию.

## Реальные источники данных

Актуальная реализация Weekly считает данные не из legacy Google Sheets-формул, а из БД:

- `raw_bot_users` — funnel и cohort метрики;
- `telegram_chat_memberships` — `channel_subscribed` и `saloon`;
- `budget_weekly` — бюджет;
- `employee_registry` — исключение внутренних пользователей.

Это реализовано в:

- `backend/app/services/roistat_weekly_parts/roistat_weekly_report_data_funnel.py`
- `backend/app/services/roistat_weekly_parts/roistat_weekly_report_data_metrics.py`
- `backend/app/services/roistat_weekly_parts/roistat_weekly_report_data_cohort.py`

## Как строится отчёт

```mermaid
flowchart TD
    A[Query params] --> B{mode}
    B -->|event| C[без cohort ids]
    B -->|first_touch| D[load first_touch cohort]
    B -->|last_touch| E[load last_touch cohort]
    C --> F[weekly cohort funnel]
    D --> F
    E --> F
    F --> G[mid funnel counts]
    G --> H[subscription counts]
    H --> I[total bot starts]
    I --> J[budget map]
    J --> K[WeeklyRow[]]
```

## WeeklyRow: состав строки

Поля собираются в `WeeklyRow`:

- `week_start`
- `almanah_starts`
- `new_in_system`
- `old_in_system`
- `platform`
- `learning`
- `started_learning`
- `base`
- `mtt`
- `spin`
- `cash`
- `not_started`
- `channel_subscribed`
- `saloon`
- `completed_course`
- `distance_grinding`
- `contract_signed`
- `budget`
- служебные/доп. поля: `direct_source_cnt`, `entered_all`, `interview_reached`, `offer_received`, `completed_*`, `contract_*`

## Логика метрик

### `almanah_starts`

Считается по `raw_bot_users.created_at` для `lead%`-ботов, с исключением внутренних пользователей и части специальных lead-строк.

Источник:

- `raw_bot_users`

Реализация:

- `roistat_weekly_report_data_funnel.py::_load_weekly_cohort_funnel`

### `new_in_system` / `old_in_system`

Для cohort по lead-стартам определяется:

- первый момент появления пользователя в системе;
- если `first_seen_at_system == lead_date`, это `new_in_system`;
- если раньше, это `old_in_system`.

### `platform`

Считается по `MIN(platform_registered_at)` на пользователя.

### `learning`

Считается по первой дате course touch:

- `COALESCE(learn_start_date, platform_registered_at)` с фильтром на непустой `start_course`.

### `started_learning`

Считается отдельно по `MIN(learn_start_date)`.

### `base`, `mtt`, `spin`, `cash`

Определяются через `start_course`:

- `LIKE 'base%'`
- `LIKE 'mtt%'`
- `LIKE 'spin%'`
- `LIKE 'cash%'`

### `not_started`

Пользователь попал на платформу, но по user-level флагам не имеет `learn_start_date`.

### `channel_subscribed` / `saloon`

Считаются из `telegram_chat_memberships.joined_at`:

- `channel_subscribed` — по `settings.telegram_channel_id`
- `saloon` — по `settings.telegram_community_id`

Источник:

- `telegram_chat_memberships`

Важно:

- используется `COUNT(DISTINCT tg_user_id)`;
- если ID чата не задан в env, значение будет `0`.

### `completed_course`, `distance_grinding`, `contract_signed`

Считаются дополнительным mid-funnel запросом по `raw_bot_users`, где cohort привязывается к неделе `learn_start_date`.

## Бюджет

Weekly использует:

- `budget_weekly`

Текущая реализация:

- агрегирует `SUM(amount)` по `DATE_TRUNC('week', week_start)`.

Источник:

- `backend/app/services/roistat_weekly_parts/roistat_weekly_report_data_metrics.py::_load_budgets`

Примечание:

- в текущем Weekly budget берётся из `budget_weekly`;
- логика fallback на `ad_metrics_weekly spend` относится к другим витринам и старым версиям weekly-описания, но не к текущему сервису `RoistatWeeklyReport`.

## Исключения и ограничения

- `employee_registry` исключается почти из всех cohort/funnel расчётов.
- Исключённые bot keys нормализуются через `normalized_excluded_bot_keys()`.
- `lead`-строки с прямыми PH identity обрабатываются отдельно как `direct_source_cnt`.

## Проверка Weekly

Для ручной DoD-проверки использовать:

- `docs/WEEKLY_CHECK.md`

Но при сверке важно помнить:

- документ проверки должен интерпретироваться вместе с текущей SQL-реализацией в `roistat_weekly_parts/*`;
- если UI и SQL расходятся, первичный источник истины сейчас — backend service, а не старая wiki-страница.
