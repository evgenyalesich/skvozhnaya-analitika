# Основной отчет

Вкладка в UI:
- `main`
- [OverviewPage.tsx](/home/fervuld/prod/analytic-system/frontend/src/pages/OverviewPage.tsx:111)
- [MainReportTable.tsx](/home/fervuld/prod/analytic-system/frontend/src/components/MainReportTable.tsx:1)

Главный endpoint:
- `/api/reports/roistat-weekly/companies-weekly`
- [reports.py](/home/fervuld/prod/analytic-system/backend/app/api/routers/reports.py:624)

## Что показывает вкладка

Это основной сводный отчет по неделям и рекламным компаниям.

Структура ответа:
- `rows` — строки по схеме `неделя -> компания`;
- `bot_rows` — строки по схеме `неделя -> компания -> бот`;
- `week_totals` — недельные тоталы по всем строкам.

На фронте данные кешируются в `localStorage` на 12 часов:
- [useMainReport.ts](/home/fervuld/prod/analytic-system/frontend/src/hooks/useMainReport.ts:4)

На backend отчет кешируется в Redis:
- [reports.py](/home/fervuld/prod/analytic-system/backend/app/api/routers/reports.py:642)

## Основная семантика

Отчет поддерживает два независимых режима:
- `mode = event | first_touch | last_touch`
- `display_mode = weekly | cohort`

### mode

`event`:
- считаем по фактической дате события.

`first_touch`:
- пользователь попадает в когорту первого касания.

`last_touch`:
- пользователь попадает в когорту последнего касания.

### display_mode

`weekly`:
- обычный недельный отчет.

`cohort`:
- те же стадии и метрики, но с когорной логикой по выбранному touch mode.

## Источники данных

Основа основного отчета:
- `raw_bot_users`
- `budget_weekly`
- `telegram_subscription_events`
- `employee_registry`

Для части данных есть дополнительная логика через Google Sheets / сервисы Roistat weekly:
- [roistat_weekly_report.py](/home/fervuld/prod/analytic-system/backend/app/services/roistat_weekly_report.py:1)

Но текущая “живая” витрина по компаниям строится прямо в router SQL:
- [reports.py](/home/fervuld/prod/analytic-system/backend/app/api/routers/reports.py:624)

## Какие колонки есть в отчете

Базовые колонки ответа:
- `budget`
- `entered_all`
- `almanah_starts`
- `direct_source_cnt`
- `new_in_system`
- `old_in_system`
- `platform_cnt`
- `learning`
- `started_learning`
- `mtt`
- `spin`
- `cash`
- `base`
- `not_started`
- `channel_subscribed`
- `saloon`
- `completed_course`
- `completed_mtt`
- `completed_spin`
- `completed_cash`
- `completed_base`
- `interview_reached`
- `offer_received`
- `contract_signed`
- `contract_mtt`
- `contract_spin`
- `contract_cash`
- `distance_grinding`

Типы на фронте:
- [useMainReport.ts](/home/fervuld/prod/analytic-system/frontend/src/hooks/useMainReport.ts:7)

## Как понимать каждую ключевую колонку

### budget

Сумма бюджета по неделе/компании/боту.

Используется дальше как база для CPA-метрик на фронте:
- `$ старта = budget / entered_all`
- `$ Альманах = budget / almanah_starts`
- `$ ПХ = budget / platform_cnt`
- `$ начала курса = budget / started_learning`
- `$ дошли до конца = budget / completed_course`
- `$ контракт = budget / contract_signed`

Где считается отображение:
- [MainReportTable.tsx](/home/fervuld/prod/analytic-system/frontend/src/components/MainReportTable.tsx:97)

### entered_all

Все уникальные старты в бот.

Это верх воронки.

### almanah_starts

Пользователи, дошедшие до lead/almanah стадии.

Важно:
- это не просто `converted_to_lead`;
- логика в проекте уже ушла к более строгому определению lead transition.

### direct_source_cnt

Пользователи из прямого источника.

Практически это те регистрации, которые пришли не через обычный бот-флоу, а через lead/direct source слой.

### new_in_system / old_in_system

Разделение на новых и старых относительно первой даты появления пользователя в системе.

### platform_cnt

Регистрация на PokerHub, уже по `ph_user_id`.

### learning и started_learning

В отчете есть оба поля, но operationally вкладка опирается на `started_learning` как на “старт обучения”.

### mtt / spin / cash / base / not_started

Разбивка пользователей по стартовому курсу.

Смысл:
- кто пошел в `MTT`
- кто пошел в `SPIN`
- кто пошел в `CASH`
- кто попал в `BASE`
- кто не начал курс

### channel_subscribed / saloon

Подписки на telegram-канал и комьюнити.

### completed_course

Пользователь завершил курс корректно:
- `completed_course = true`
- `completed_course_at IS NOT NULL`
- `completed_course_at >= created_at`

### interview_reached / offer_received / contract_signed / distance_grinding

Финальные бизнес-стадии воронки найма.

### completed_mtt / completed_spin / completed_cash / completed_base

Разрез completed course по типу курса.

### contract_mtt / contract_spin / contract_cash

Разрез контрактов по типу курса.

## Производные KPI на фронте

Именно фронт рассчитывает часть KPI-колонок:
- `% ПХ = platform_cnt / almanah_starts * 100`
- `% обуч. = started_learning / platform_cnt * 100`
- `% курса = completed_course / started_learning * 100`
- `% предофер = interview_reached / started_learning * 100`
- `% офер = offer_received / interview_reached * 100`
- `% контракт = contract_signed / completed_course * 100`

Где это видно:
- [MainReportTable.tsx](/home/fervuld/prod/analytic-system/frontend/src/components/MainReportTable.tsx:97)

## Нормализация компании

Пустая или мусорная компания нормализуется в:
- `Без категории`

Значения, которые приводятся к `Без категории`:
- `NULL`
- пустая строка
- `-`
- `—`
- `(none)`
- `none`
- `null`
- `нет метки`

Где видно:
- [report_repository.py](/home/fervuld/prod/analytic-system/backend/app/services/report_repository.py:177)
- [reports.py](/home/fervuld/prod/analytic-system/backend/app/api/routers/reports.py:672)

## Критичные нюансы

- UTM фильтры работают и по обычным `utm_*`, и по `platform_utm_*`.
- excluded bots вырезаются до расчета.
- сотрудники исключаются через `employee_registry`.
- кеш может временно отдавать stale-версию отчета, если идет пересчет.

## Что проговорить на созвоне

- Где метрика считается по `tg_user_id`, а где по `ph_user_id`.
- Какие KPI реально считает backend, а какие дорисовывает frontend.
- Почему одна и та же неделя в `event` и `first_touch/last_touch` может давать разный состав пользователей.
- Почему строка может попасть в `Без категории`, даже если в исходнике было “какое-то” значение компании.
