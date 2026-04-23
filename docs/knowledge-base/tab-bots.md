# BOTs

Эта вкладка в UI живёт под ключом `totalb`, но по смыслу это витрина `BOTs`:
- [OverviewPage.tsx](/home/fervuld/prod/analytic-system/frontend/src/pages/OverviewPage.tsx:111)
- [FunnelSummaryTable.tsx](/home/fervuld/prod/analytic-system/frontend/src/components/FunnelSummaryTable.tsx:1)

## Что показывает вкладка

Вкладка показывает воронку по ботам:
- сколько пользователей вошло в бот;
- сколько из них дошло до Альманаха;
- сколько зарегистрировалось на PokerHub;
- сколько стартовало обучение;
- сколько завершило курс;
- сколько дошло до интервью, оффера, контракта и наигрыша дистанции.

На фронте это таблица `FunnelSummaryTable`, а источник данных:
- при `touch_mode = event` и `group_by = bot_key` через `summary`-логику и `main report`;
- дополнительно общий stage total подгружается из `/api/reports/funnel-start/stages`.

Связанные endpoints:
- `/api/reports/funnel-start/summary`
- `/api/reports/funnel-start/stages`
- `/api/reports/weekly-filtered`
- [reports.py](/home/fervuld/prod/analytic-system/backend/app/api/routers/reports.py:245)

## Главный источник данных

Источник истины для живых цифр:
- `raw_bot_users`

Почему не weekly aggregate:
- [report_repository.py](/home/fervuld/prod/analytic-system/backend/app/services/report_repository.py:27)

Функция `_can_use_weekly_bot_agg(...)` всегда возвращает `False`, потому что старый агрегат работает по старой семантике:
- UTC-даты;
- старое определение lead;
- неконсистентный переход между `tg_user_id` и `ph_user_id`.

## Какие фильтры влияют

Общие фильтры:
- период `start_date/end_date`;
- `bots`;
- `advertising_companies`;
- `utm_source/utm_campaign/utm_medium/utm_content/utm_term`;
- `user_scope`;
- `touch_mode`.

Где собираются:
- [report_filters.py](/home/fervuld/prod/analytic-system/backend/app/api/report_filters.py:10)
- [useReports.ts](/home/fervuld/prod/analytic-system/frontend/src/hooks/useReports.ts:103)

Критичные нюансы:
- UTM фильтры проверяются и по `utm_*`, и по `platform_utm_*`.
- сотрудники из `employee_registry` исключаются;
- excluded bots вырезаются на уровне репозитория;
- дата почти везде нормализуется в `Europe/Moscow`.

Где это видно:
- [report_repository.py](/home/fervuld/prod/analytic-system/backend/app/services/report_repository.py:38)
- [report_repository.py](/home/fervuld/prod/analytic-system/backend/app/services/report_repository.py:74)
- [report_repository.py](/home/fervuld/prod/analytic-system/backend/app/services/report_repository.py:136)

## Как считаются стадии

Строгая последовательность стадий:
- `entered -> lead -> platform -> learning -> course -> interview -> passed -> offer`

Отдельные ответвления:
- `simulator` идет от `course`;
- `distance_grinding` идет от `offer`;
- `contract` идет от `offer`.

Определено здесь:
- [report_repository.py](/home/fervuld/prod/analytic-system/backend/app/services/report_repository.py:101)

### entered

Формула:
- `COUNT(DISTINCT tg_user_id)`

Это количество уникальных пользователей, вошедших в бот.

### lead

Формула не равна просто `converted_to_lead = true`.

Используется `lead transition condition`:
- у этого же `tg_user_id` существует запись `lead%`;
- дата lead-записи не раньше опорной записи;
- сравнение идёт по МСК-дате.

Где определяется:
- [report_repository.py](/home/fervuld/prod/analytic-system/backend/app/services/report_repository.py:84)

### platform

Формула:
- `COUNT(DISTINCT ph_user_id)` при выполнении:
- `ph_user_id IS NOT NULL`
- `registered_platform = true`
- `platform_registered_at IS NOT NULL`

### learning

Формула:
- `platform AND started_learning = true`

Считается уже по `ph_user_id`.

### course

Формула:
- `learning AND completed_course = true AND completed_course_at IS NOT NULL AND completed_course_at >= created_at`

Это важный нюанс: просто флаг `completed_course = true` недостаточен.

### interview / passed / offer / contract / distance_grinding

Формулы:
- `interview = course AND interview_reached = true`
- `passed = interview AND interview_passed = true`
- `offer = passed AND offer_received = true`
- `contract = offer AND contract_signed = true`
- `distance_grinding = offer AND distance_grinding = true`

## Как делится на новых и старых

`new_in_system`:
- первый вход пользователя в систему совпадает с датой его входа в текущий бот.

`old_in_system`:
- первый вход в систему раньше даты текущего входа в бот.

Для touch-режимов сравнение делается не с текущей строкой, а с датой первого входа в attributed bot.

Где видно:
- [report_repository.py](/home/fervuld/prod/analytic-system/backend/app/services/report_repository.py:156)
- [report_repository.py](/home/fervuld/prod/analytic-system/backend/app/services/report_repository.py:806)

## Touch mode

Поддерживаются режимы:
- `event`
- `first_touch`
- `last_touch`

Смысл:
- `event` считает по фактической записи `raw_bot_users`;
- `first_touch` переатрибутирует пользователя к первому боту;
- `last_touch` переатрибутирует пользователя к последнему боту перед стартом обучения.

Где считается touch summary:
- [report_repository.py](/home/fervuld/prod/analytic-system/backend/app/services/report_repository.py:225)

Особенно важно:
- в `last_touch` дата фильтрации идет через дату первой записи в `last_touch_bot`;
- split `new/old` тоже пересчитывается относительно attributed bot.

## Что проговорить на созвоне

- Почему `lead` здесь больше не равен простому флагу `converted_to_lead`.
- Почему начиная с `platform` метрики переходят на `ph_user_id`.
- Почему excluded bots и `employee_registry` делают цифры меньше, чем “сырые count(*) из таблицы”.
- Почему `event` и `first/last touch` могут сильно расходиться на одних и тех же пользователях.
