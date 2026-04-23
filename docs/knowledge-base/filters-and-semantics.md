# Filters And Semantics

## Общие фильтры

Общий набор фильтров задаётся тут:
- [report_filters.py](/home/fervuld/prod/analytic-system/backend/app/api/report_filters.py:10)
- [useReports.ts](/home/fervuld/prod/analytic-system/frontend/src/hooks/useReports.ts:6)

Основные поля:
- `start_date`, `end_date`
- `bots`
- `advertising_companies`
- `utm_source`
- `utm_campaign`
- `utm_medium`
- `utm_content`
- `utm_term`
- `user_scope`

Ограничение диапазона:
- максимум `730` дней
- [report_filters.py](/home/fervuld/prod/analytic-system/backend/app/api/report_filters.py:7)

## Важная семантика дат

Во многих живых отчётах дата нормализуется в МСК:
- [report_repository.py](/home/fervuld/prod/analytic-system/backend/app/services/report_repository.py:64)

Используется helper:
- `_msk_date(column)`

Это важно, потому что часть логики считает дату через:
- `(created_at AT TIME ZONE 'Europe/Moscow')::date`
- или `timezone('Europe/Moscow', column)::date`

## User Scope

`user_scope`:
- `all`
- `new`
- `old`

Как определяется:
- `new`: дата первого появления пользователя в системе равна дате текущей записи
- `old`: дата первого появления в системе меньше даты текущей записи

Код:
- [report_repository.py](/home/fervuld/prod/analytic-system/backend/app/services/report_repository.py:139)

## UTM семантика

Во многих отчётах фильтр работает не только по `utm_*`, но и по `platform_utm_*`.

Код:
- [report_repository.py](/home/fervuld/prod/analytic-system/backend/app/services/report_repository.py:36)

Практический смысл:
- если UTM есть либо в первичном источнике, либо в platform-полях, запись может попасть в выборку.

## Исключение сотрудников

Почти все живые отчёты исключают пользователей из `employee_registry`.

Код:
- [report_repository.py](/home/fervuld/prod/analytic-system/backend/app/services/report_repository.py:156)

Это критично при сверке с сырыми выгрузками из БД.

## Исключённые боты

Во многих отчётах применяются `normalized_excluded_bot_keys()`.

Код:
- [report_repository.py](/home/fervuld/prod/analytic-system/backend/app/services/report_repository.py:16)
- [reports.py](/home/fervuld/prod/analytic-system/backend/app/api/routers/reports.py:656)

Следствие:
- не каждый бот из `raw_bot_users` реально участвует в аналитике.

## Touch Mode

В системе есть несколько режимов атрибуции:
- `event`
- `first_touch`
- `last_touch`

Где видно на фронте:
- [useReports.ts](/home/fervuld/prod/analytic-system/frontend/src/hooks/useReports.ts:16)

Практический смысл:
- `event` — фильтрация по дате события/записи;
- `first_touch` — когорта по первой точке касания;
- `last_touch` — когорта по последней точке касания.

## Raw filters

Для `funnel-start/raw` есть отдельный большой набор `raw_*` фильтров:
- статусные булевы поля;
- статусы интервью/оффера/контракта;
- фильтры по подписке/сообществу;
- наличие first/last touch;
- сегменты source category.

Код:
- [report_filters.py](/home/fervuld/prod/analytic-system/backend/app/api/report_filters.py:43)
- [useReports.ts](/home/fervuld/prod/analytic-system/frontend/src/hooks/useReports.ts:147)

Отдельный нюанс:
- выбор `lead` и `__direct_source__` на фронте мапится не только в `raw_bot_key`, но и в `raw_source_category`.
