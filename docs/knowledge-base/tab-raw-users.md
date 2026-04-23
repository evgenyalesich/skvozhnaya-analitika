# Raw users

Вкладка в UI:
- `raw`
- [OverviewPage.tsx](/home/fervuld/prod/analytic-system/frontend/src/pages/OverviewPage.tsx:478)
- [RawUsersTable.tsx](/home/fervuld/prod/analytic-system/frontend/src/components/RawUsersTable.tsx:1)

Backend:
- `/api/reports/funnel-start/raw`
- `/api/reports/funnel-start/export`
- [reports.py](/home/fervuld/prod/analytic-system/backend/app/api/routers/reports.py:369)

Основной сервис:
- [raw_user_repository.py](/home/fervuld/prod/analytic-system/backend/app/services/raw_user_repository.py:1)

## Что это за вкладка

Это не агрегат, а построчная витрина пользователей из `raw_bot_users`, поверх которой достраиваются вычисляемые поля и часть справочных данных.

Используется для:
- детальной сверки цифр;
- поиска конкретного пользователя;
- понимания, почему пользователь попал или не попал в стадию;
- экспорта сырых строк в CSV.

## Источники данных

База:
- `raw_bot_users`

Дополнительные источники:
- `bot_registry` для canonical base;
- `PhUserMirrorReplica` для зеркальных полей PokerHub;
- `budget_weekly` для расчетного `budget`;
- `employee_registry` для исключения сотрудников.

Где видно:
- [raw_user_repository.py](/home/fervuld/prod/analytic-system/backend/app/services/raw_user_repository.py:94)
- [raw_user_repository.py](/home/fervuld/prod/analytic-system/backend/app/services/raw_user_repository.py:165)
- [raw_user_repository.py](/home/fervuld/prod/analytic-system/backend/app/services/raw_user_repository.py:191)

## Какие фильтры работают

### Верхние фильтры вкладки

Они такие же, как у остальных отчетов:
- период;
- bots;
- advertising_companies;
- utm;
- touch mode.

Важно:
- `Raw users` уважает верхние фильтры, включая выбранного бота;
- touch mode передается отдельно как `touch_mode`.

Где видно:
- [useRawUsers.ts](/home/fervuld/prod/analytic-system/frontend/src/hooks/useRawUsers.ts:1)

### Внутренние raw-фильтры

Поддерживаются:
- `raw_bot_key`
- `raw_tg_user_id`
- `raw_utm_*`
- `raw_advertising_company`
- статусы стадий и их text-status поля
- `raw_channel_subscribed`
- `raw_community_member`
- `raw_team_member`
- `raw_internal_status`
- `raw_user_block`
- `raw_user_status`
- `raw_first_touch_present`
- `raw_last_touch_present`
- `raw_source_category`

Где описаны:
- [report_filters.py](/home/fervuld/prod/analytic-system/backend/app/api/report_filters.py:146)

## Как работает touch mode

Поддерживаются:
- `event`
- `first`
- `last`

Смысл:
- `event` — фильтрация и вычисления идут по текущей строке `raw_bot_users`;
- `first` — выборка и user freshness переатрибутируются к `first_touch_bot`;
- `last` — выборка и freshness переатрибутируются к `last_touch_bot`.

Критичный нюанс:
- в raw режиме базовый фильтр по bot всегда применяется к `row.bot_key`;
- а в `first/last` дополнительно требуется совпадение с touch attribution bot.

Где это видно:
- [raw_user_repository.py](/home/fervuld/prod/analytic-system/backend/app/services/raw_user_repository.py:364)

## Как вычисляются важные поля

### first_seen_at_system

Минимальный `created_at` по `tg_user_id`.

### first_seen_at_bot

Минимальный `created_at` по паре:
- `tg_user_id`
- `bot_key`

### new_in_system / old_in_system

`event`:
- сравнение идет с текущим `created_at`.

`first/last`:
- сравнение идет с датой attributed bot.

### new_in_bot

`event`:
- текущий canonical base совпадает с `first_touch_canonical_base`.

`first/last`:
- приравнивается к `new_in_system`.

### budget

Здесь `budget` не является полем сырой строки.

Это расчетный показатель:
- берется `CPA learning` на дату `learn_start_date`;
- ключ матчинга: `day + campaign + bot_key`;
- если bot-specific budget не найден, берется `day + campaign + ''`.

Где видно:
- [raw_user_repository.py](/home/fervuld/prod/analytic-system/backend/app/services/raw_user_repository.py:191)
- [raw_user_repository.py](/home/fervuld/prod/analytic-system/backend/app/services/raw_user_repository.py:662)

### completed_course

Это тоже не просто копия поля.

Формула:
- `completed_course = true`
- `completed_course_at IS NOT NULL`
- `completed_course_at >= created_at`

### course_duration_days

Формула:
- `completed_course_at.date - learn_start_date.date`

Только если обе даты есть и `completed_course_at >= learn_start_date`.

### registered_platform

Сериализация усиливает сырое значение:
- `registered_platform = user.registered_platform OR mirror is not None`

То есть mirror join может “доказать” платформу, даже если флаг в сырой строке пустой.

## Source category

Вкладка делит источники на:
- `bot_source`
- `almanah`
- `direct_source`

Где определяется:
- [raw_user_repository.py](/home/fervuld/prod/analytic-system/backend/app/services/raw_user_repository.py:49)

Логика:
- `lead` + `abs(tg_user_id) == ph_user_id` => `direct_source`
- `lead`, но TG и PH не совпали => `almanah`
- все остальные => `bot_source`

Дополнительно:
- если `tg_user_id < 0` и есть `ph_user_id`, это тоже `direct_source`

## Mirror dedup для lead

Для synthetic mirror lead rows есть специальная защита от дублей.

Смысл:
- все не-lead строки оставляем;
- реальные lead строки оставляем;
- synthetic lead с `tg_user_id < 0` оставляем только если нет соответствующего real lead.

Где видно:
- [raw_user_repository.py](/home/fervuld/prod/analytic-system/backend/app/services/raw_user_repository.py:65)

Это одна из главных причин, почему “simple select from raw_bot_users where bot_key = lead” может не совпасть с вкладкой.

## Особенности отображения в UI

### Прямой источник

Для `source_category = direct_source`:
- в UI скрывается `TG ID`;
- `pokerhub_user_id` показывается из `ph_user_id`.

Где видно:
- [reports.py](/home/fervuld/prod/analytic-system/backend/app/api/routers/reports.py:380)

### База

Во фронте колонка `База` переименовывает некоторые значения:
- `direct_source` => `Прямой источник`
- `lead + almanah` => `Альманах`

Где видно:
- [RawUsersTable.tsx](/home/fervuld/prod/analytic-system/frontend/src/components/RawUsersTable.tsx:320)

## Сортировка и экспорт

По умолчанию:
- `sort_by = created_at`
- `sort_direction = desc`

Где задается:
- [report_filters.py](/home/fervuld/prod/analytic-system/backend/app/api/report_filters.py:135)

Экспорт:
- идет пакетами по 500 строк;
- выгружает CSV из того же `fetch_raw`, что и таблица;
- значит экспорт и экран должны совпадать по фильтрам и сортировке.

Где видно:
- [reports.py](/home/fervuld/prod/analytic-system/backend/app/api/routers/reports.py:398)

## Что проговорить на созвоне

- Почему `budget` на raw строке расчетный, а не физически лежит в `raw_bot_users`.
- Почему `registered_platform` может стать `true` через mirror join.
- Почему direct source строки показывают `PokerHub ID`, но без `TG ID`.
- Почему `completed_course` на вкладке строже, чем просто сырое булево поле.
