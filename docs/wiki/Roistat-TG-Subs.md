# Вкладка TG SUBS

## Что показывает

- Сравнение стартов ботов и подписок.
- Канал и салун в разрезе РК и ботов.
- Таблица и график.

## Файлы

- `frontend/src/components/SubscriptionsComparePanel.tsx`.
- `frontend/src/hooks/useSubscriptionsCompare.ts`.
- `backend/app/services/report_repository.py`.

## API

- `GET /api/reports/subscriptions/compare`.

## Источники данных

- Таблица `agg_tg_subs_daily`.
- Справочник `advertising_companies`.

## Логика агрегации на бэке

- Группировка по дням или неделям.
- В режиме `campaign` учитываются только активные РК.
- `channel_total = max(subscribed - unsubscribed, 0)`.
- `saloon_total = max(subscribed - unsubscribed, 0)`.

## Параметры фильтрации

- `start_date`, `end_date`.
- `bots`.
- `advertising_companies`.
- `utm_source`, `utm_campaign`, `utm_medium`, `utm_content`, `utm_term`.

## UI особенности

- `Интервал`: `По дням` или `По неделям`.
- При `По неделям` доступен фильтр `Месяц`.
- Чекбоксы управляют видимостью метрик в графике и таблице.
- Раскрытие РК показывает боты, раскрытие бота показывает строки по датам.

## Важно

- В коде UI группировка всегда по кампании, переключатель не выведен.
- Значения канала и салуна зависят от `TELEGRAM_CHANNEL_ID` и `TELEGRAM_COMMUNITY_ID` при построении агрегата.
