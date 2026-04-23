# Formulas And KPI

## Funnel Start

### Total

Код:
- [report_repository.py](/home/fervuld/prod/analytic-system/backend/app/services/report_repository.py:473)

Формулы:
- `total_users = COUNT(DISTINCT tg_user_id)`
- `total_budget = SUM(budget)`
- `cac = total_budget / total_users`

### Daily

Код:
- [report_repository.py](/home/fervuld/prod/analytic-system/backend/app/services/report_repository.py:489)

Формулы:
- группировка по `date_trunc('day', created_at)`
- `users = COUNT(DISTINCT tg_user_id)`
- `budget = SUM(budget)`

### Breakdown

Код:
- [report_repository.py](/home/fervuld/prod/analytic-system/backend/app/services/report_repository.py:509)

Формулы:
- `utm_source` берётся как `COALESCE(platform_utm_source, utm_source, '—')`
- `utm_campaign` берётся как `COALESCE(platform_utm_campaign, utm_campaign, '—')`
- `users = COUNT(DISTINCT tg_user_id)`
- `budget = SUM(budget)`

### Conversions

Код:
- [report_repository.py](/home/fervuld/prod/analytic-system/backend/app/services/report_repository.py:544)

Формулы:
- `entered = COUNT(DISTINCT tg_user_id)` по боту
- `converted = COUNT(DISTINCT tg_user_id)` с lead-transition условием
- `conversion_rate = converted / entered * 100`

Что считается lead-transition:
- у пользователя существует lead-запись;
- lead-запись не раньше текущей опорной записи;
- сравнение делается по МСК-дате.

Код условия:
- [report_repository.py](/home/fervuld/prod/analytic-system/backend/app/services/report_repository.py:71)

### Stages

Код:
- [report_repository.py](/home/fervuld/prod/analytic-system/backend/app/services/report_repository.py:604)

Строгая последовательность:
- `entered -> lead -> platform -> learning -> course -> interview -> passed -> offer`

Дополнительно:
- `simulator` ответвляется от `course`
- `distance_grinding` и `contract` ответвляются от `offer`

Код:
- [report_repository.py](/home/fervuld/prod/analytic-system/backend/app/services/report_repository.py:95)

Условия:
- `platform`: есть `ph_user_id`, `registered_platform = true`, `platform_registered_at != null`
- `learning`: `platform` + `started_learning = true`
- `course`: `learning` + `completed_course = true` + `completed_course_at >= created_at`
- `interview`: `course` + `interview_reached = true`
- `passed`: `interview` + `interview_passed = true`
- `offer`: `passed` + `offer_received = true`
- `distance_grinding`: `offer` + `distance_grinding = true`
- `contract`: `offer` + `contract_signed = true`

Нюанс:
- `platform` и дальнейшие стадии часто считаются по `COUNT(DISTINCT ph_user_id)`, а не `tg_user_id`.

## Main Report / Roistat Weekly

Главный endpoint:
- [reports.py](/home/fervuld/prod/analytic-system/backend/app/api/routers/reports.py:624)

Поля, которые точно есть в ответе:
- `entered_all`
- `budget`
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
- `interview_reached`
- `offer_received`
- `contract_signed`
- `distance_grinding`

UI-тип ответа:
- [useMainReport.ts](/home/fervuld/prod/analytic-system/frontend/src/hooks/useMainReport.ts:7)

Ключевая семантика:
- отчёт кешируется в Redis;
- поддерживает режимы `event`, `first_touch`, `last_touch`;
- поддерживает `weekly` и `cohort` display mode;
- компания нормализуется в `Без категории`, если значение пустое/мусорное.

## Subscriptions Compare

Код:
- [report_repository.py](/home/fervuld/prod/analytic-system/backend/app/services/report_repository.py:976)

Параметры:
- `group_by = campaign | bot | overall`
- `interval = day | week`

Источник:
- `tg_subs_daily_agg`
- `telegram_subscription_events`
- `raw_bot_users`

Смысл:
- сравниваются старты, подписки, отписки, активная база и snapshot-срезы по channel/community.

## Course Mix

Код:
- [report_repository.py](/home/fervuld/prod/analytic-system/backend/app/services/report_repository.py:2085)

Формула:
- берутся записи `started_learning = true`
- группировка по `COALESCE(start_course, 'UNKNOWN')`

## Touch Summary

Код:
- [report_repository.py](/home/fervuld/prod/analytic-system/backend/app/services/report_repository.py:2120)

Формула:
- группировка по `first_touch_*` или `last_touch_*`
- `users = COUNT(DISTINCT tg_user_id)`

Нюанс:
- для `last` используется дата `learn_start_date`
- для `first` используется `created_at`

## Touch Funnel Summary

Код:
- [report_repository.py](/home/fervuld/prod/analytic-system/backend/app/services/report_repository.py:2177)

Поля:
- `entered`
- `interview`
- `passed`
- `offer`
- `distance_grinding`
- `contract`

Группировка:
- по `first_touch_bot` или `last_touch_bot`

## Budget Weekly

Код:
- [report_repository.py](/home/fervuld/prod/analytic-system/backend/app/services/report_repository.py:2315)

Что собирается в одну строку:
- бюджет из `budget_weekly`
- стадии из `raw_bot_users`
- подписки из `telegram_subscription_events`
- course mix из `raw_bot_users`
- ad metrics из `ad_metrics_weekly`

Производные KPI:
- `cpf = spend_base / subscribed`
- `cpl = spend_base / lead`
- `cpa = spend_base / learning`
- `cpc = spend_base / contract`
- `ctr = clicks / impressions * 100`
- `cpc_click = spend_base / clicks`
- `cpm = spend_base / impressions * 1000`

Где:
- `spend_base = spend`, если `spend > 0`
- иначе `spend_base = budget`

Код:
- [report_repository.py](/home/fervuld/prod/analytic-system/backend/app/services/report_repository.py:2565)

## Что обязательно проговорить на созвоне

- Что считается по `tg_user_id`, а что по `ph_user_id`.
- Где дата берётся по МСК, а где напрямую из timestamp.
- Где фильтр по UTM использует `platform_utm_*`, а где нет.
- Где компания нормализуется в `Без категории`.
- Почему weekly aggregate сейчас не источник истины для живых витрин.
