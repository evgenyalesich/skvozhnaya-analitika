# Вкладка TotalA

## Что показывает

- Таблица воронки по рекламным компаниям.
- Привязанные боты для каждой РК.
- Дополнительные рекламные метрики и бюджеты.

## Файлы

- `frontend/src/components/FunnelSummaryTable.tsx`.
- `frontend/src/hooks/useFunnelSummary.ts`.
- `frontend/src/hooks/useBudgetWeeklyReport.ts`.
- `frontend/src/hooks/useAdvertisingCompanies.ts`.

## API

- `GET /api/reports/funnel-start/summary?group_by=advertising_company`.
- `GET /api/advertising-companies`.
- `GET /api/reports/budgets/weekly`.
- `GET /api/reports/weekly?group_by=company&group_key=...`.

## Источники данных

- `raw_bot_users` для воронки.
- `advertising_companies` для справочника РК и привязок ботов.
- `budget_weekly` и `ad_metrics_weekly` для рекламных метрик.

## Особенности логики

- В таблицу добавляются РК из справочника, даже если по ним нет данных в воронке.
- РК со значениями `-`, `—`, `(none)`, `none`, `null` исключаются.
- Метрики бюджета агрегируются по названию кампании.

## Кнопки и действия

- Сортировка по клику на заголовок колонки.
- `Скачать CSV` формирует CSV на фронте из текущих строк.
- Раскрытие строки показывает понедельную статистику.

## Понедельная статистика

- Источник: `GET /api/reports/weekly`.
- Данные берутся из Redis ключей `reports:weekly:*`.
- Если кэш не заполнен, таблица будет пустая.
