# Roistat Weekly (экран в дашборде)

## Точка входа в UI

Экран: таб `WEEKLY`.

Файлы фронта:

- `frontend/src/pages/OverviewPage.tsx`
- `frontend/src/hooks/useRoistatWeekly.ts`
- `frontend/src/components/WeeklyTable.tsx`

Элементы управления:

- Дропдаун "Месяц":
  - Влияет на то, какие строки из ответа показываются.
  - Также задает дефолтный диапазон `first_touch_start/end`, если включен тумблер first_touch и глобальные даты не выбраны.
- Тумблер `Фильтр first_touch`:
  - Выключен: weekly-строки по всем пользователям.
  - Включен: weekly-строки по когорте пользователей, у которых first touch попадает в выбранный диапазон.

## API-контракт

Метод:

- `GET /api/reports/roistat-weekly`

Query params:

- `mode`: `event` или `first_touch`
- `event_start`, `event_end`: опциональный фильтр по "датам событий" (по данным из source sheet)
- `first_touch_start`, `first_touch_end`: опциональный фильтр по диапазону first_touch для формирования когорты

Логика запроса на фронте:

- Реализовано в `frontend/src/hooks/useRoistatWeekly.ts`.
- Когда включен тумблер first_touch:
  - отправляется `mode=first_touch`
  - отправляется `first_touch_start/first_touch_end` (если глобальные даты не выбраны, берется диапазон выбранного месяца)
  - `event_start/event_end` отправляются только из глобальных фильтров (часто пустые)

Ответ:

- `rows: RoistatWeeklyRow[]`
- Каждая строка - один "недельный" бакет внутри месяца.

Кеширование:

- Ключ:
  - `reports:roistat_weekly:v2:{mode}:{event_start}:{event_end}:{first_touch_start}:{first_touch_end}`
- TTL:
  - `settings.weekly_cache_ttl_seconds` (по умолчанию `86400`).

## Правила бакетинга по неделям

Здесь не ISO-недели. Каждый месяц разбивается на фиксированные интервалы:

- неделя 1: дни 1..7
- неделя 2: дни 8..14
- неделя 3: дни 15..21
- неделя 4: дни 22..28
- неделя 5: дни 29..конец месяца

Реализация:

- `backend/app/services/roistat_weekly_report.py`:
  - `in_bucket()` для дат из Google Sheets
  - `week_bucket_start()` в `_load_saloon_counts()` для салуна

## Определение метрик

Основные метрики считаются из Google Sheets таба `'pokerhub_robot'!A:U`.

Используемые колонки (индексы 0-based как в коде):

- `row[0]` (A): `tg_user_id` (опционально, нужен только для фильтрации когорты)
- `row[4]` (E): `start_dt` ("Старт в бота")
- `row[7]` (H): `h_dt` (вспомогательная дата для legacy-формул)
- `row[17]` (R): `platform_dt` (регистрация/авторизация на платформе)
- `row[18]` (S): `learning_dt` (регистрация на курс)
- `row[19]` (T): `group_value` (строка, приводится к lower; классификация mtt/spin/cash и спец-правила)
- `row[20]` (U): `courses_value` (пусто означает "не начали курс")

### Старт в бота (`almanah_starts`)

- Кол-во строк, где `start_dt` попадает в бакет.
- Поле в payload называется `almanah_starts` по историческим причинам; в UI это "Старт в бота".

Источник: `'pokerhub_robot'!E`.

### Регистрация на платформе (`platform`)

- Кол-во строк, где `platform_dt` попадает в бакет.

Источник: `'pokerhub_robot'!R`.

### Регистрация на курс (`learning`)

- Кол-во строк, где `learning_dt` попадает в бакет.

Источник: `'pokerhub_robot'!S`.

### mtt (`mtt`)

- Считается только если `learning_dt` попал в бакет и подстрока `"mtt"` есть в `group_value`.

Источник: `'pokerhub_robot'!T` + `'pokerhub_robot'!S`.

### spin (`spin`)

Базовое правило:

- Считается только если `learning_dt` попал в бакет и подстрока `"spin"` есть в `group_value`, кроме недели 4 (там spin пропускается условием `week_index != 4`).

Дополнительные правила для `"лендинг. основная воронка"`:

- Неделя 2: если `learning_dt` по дате между 3..9 (включительно).
- Неделя 3: если `start_dt` попал в бакет недели 3.
- Неделя 4: если `h_dt` попал в бакет недели 4.
- Неделя 5: если `learning_dt` попал в бакет недели 5.

### cash (`cash`)

Базовое правило:

- Когда `learning_dt` попал в бакет и `"cash"` есть в `group_value`, считаем cash для всех недель, кроме 2 и 4.

Legacy-исключения по неделям:

- Неделя 2: используем `start_dt` вместо `learning_dt`.
- Неделя 4: используем `h_dt` вместо `learning_dt`.

### Не начали курс (`not_started`)

- Кол-во строк, где `learning_dt` попал в бакет и `courses_value` пустой.

### Салун (`saloon`)

Смысл:

- Кол-во подписок в салун, бакетированных в такую же "месячную сетку" недель.

Источник зависит от режима:

- Без когорты (mode != first_touch):
  - Источник: `agg_tg_subs_daily.saloon_subscribed`
  - Агрегация: суммируем `saloon_subscribed` по дням, затем складываем по бакетам месяца
  - Важно: `agg_tg_subs_daily` строится в `AggregateRefresher._rebuild_tg_subs_daily()` из `telegram_subscription_events` и уже применяет `TELEGRAM_COMMUNITY_ID` при построении агрегата.
- В режиме когорты (mode=first_touch):
  - Источник: `telegram_subscription_events`
  - Фильтр: `status='subscribed'` и `channel_id = TELEGRAM_COMMUNITY_ID`
  - Фильтр когорты: `tg_user_id IN cohort_ids`
  - Дедупликация: уникальные `tg_user_id` внутри одного недельного бакета

Реализация: `backend/app/services/roistat_weekly_report.py::_load_saloon_counts()`.

### Бюджет (`budget`)

- Таблицы-источники:
  - `budget_weekly` (план)
  - `ad_metrics_weekly` (факт spend)
- Бакетинг:
  - обе таблицы приводятся к week_start по схеме:
    - `month_start + (((day_of_month - 1) / 7) * 7)` дней
- Итог по бакету:
  - если `spend > 0`, используем spend
  - иначе используем плановый бюджет

Реализация: `backend/app/services/roistat_weekly_report.py::_load_budgets()`.

## Когорта first_touch (mode=first_touch)

Когорта выбирается из `raw_bot_users`:

- first touch date = `MIN(created_at)::date` по `tg_user_id`
- `bot_key` должен быть непустым
- исключаются некоторые bot_key и исключается `lead%`

Реализация: `backend/app/services/roistat_weekly_report.py::_load_first_touch_cohort()`.

## Важные нюансы

- Поле `almanah_starts` в этом отчете используется как "Старт в бота".
- В `agg_tg_subs_daily` нет `tg_user_id`, поэтому cohort-фильтр для салуна нельзя применить к агрегату. В режиме когорты используется сырая таблица `telegram_subscription_events`.
- Для расчета салуна нужен `TELEGRAM_COMMUNITY_ID`. Если env-переменная отсутствует, салун будет `0`.
