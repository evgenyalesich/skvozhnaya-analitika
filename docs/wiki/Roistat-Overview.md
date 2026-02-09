# Вкладка Overview

## Что показывает

- Сводные карточки.
- График `Daily New Users`.
- Таблица `Breakdown`.

## Файлы

- `frontend/src/pages/OverviewPage.tsx`.
- `frontend/src/components/MetricCard.tsx`.
- `frontend/src/components/LineChartCard.tsx`.
- `frontend/src/components/BreakdownTable.tsx`.
- `frontend/src/hooks/useReports.ts`.

## API

- `GET /api/reports/funnel-start/total`.
- `GET /api/reports/funnel-start/daily`.
- `GET /api/reports/funnel-start/breakdown`.

## Источники данных

- Таблица `raw_bot_users`.

## Логика метрик

- `Users at Funnel Start`.
- Количество уникальных `tg_user_id` после применения фильтров.

- `Total Budget`.
- Сумма `raw_bot_users.budget` после применения фильтров.

- `CAC`.
- `Total Budget / Users at Funnel Start`.

## График Daily New Users

- Бэк возвращает точки по датам `created_at`.
- Фронт достраивает пропуски нулями внутри выбранного диапазона.
- Переключатели `7 дней`, `14 дней`, `Месяц`, `Все время` управляют видимым окном.
- Поле `Дата по` задает конец окна.

## Breakdown

- Источник: `GET /api/reports/funnel-start/breakdown`.
- Группировка зависит от выбранного `group_by`.
- В этой вкладке UI не меняет `group_by` напрямую.
- Значение `group_by` наследуется из вкладки `RAW UTM`.

## Колонки таблицы Breakdown

- `Group`: значение группировки (`utm_source`, `utm_campaign`, `source_campaign`, `advertising_company`).
- `Users`: количество уникальных `tg_user_id` после фильтров.
- `Budget`: сумма `raw_bot_users.budget` после фильтров.
