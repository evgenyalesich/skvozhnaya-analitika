# Вкладка TotalC

## Что показывает

- Воронку по `FIRST TOUCH` или `LAST TOUCH`.
- Дополнительные рекламные метрики и бюджеты.
- Понедельную детализацию по выбранному touch‑боту.

## Файлы

- `frontend/src/components/TouchFunnelTable.tsx`.
- `frontend/src/hooks/useTouchFunnelSummary.ts`.
- `frontend/src/hooks/useBudgetWeeklyReport.ts`.

## API

- `GET /api/reports/touch/funnel-summary?mode=first|last`.
- `GET /api/reports/touch/weekly?group_key=...&mode=first|last`.
- `GET /api/reports/budgets/weekly`.

## Источники данных

- `raw_bot_users` для воронки.
- `budget_weekly` и `ad_metrics_weekly` для рекламных метрик.

## Логика touch

- `FIRST TOUCH` использует `first_touch_bot` и дату `created_at`.
- `LAST TOUCH` использует `last_touch_bot` и дату `learn_start_date`.
- Записи без меток (`NULL`, пусто, `нет метки`) исключаются.

## Кнопки и действия

- Переключатель `FIRST TOUCH` и `LAST TOUCH`.
- `Скачать CSV` формирует CSV на фронте.
- Раскрытие строки показывает понедельную статистику.

## Понедельная статистика

- Бэк считает `date_trunc('week', created_at|learn_start_date)`.
- Возвращается список недель, сгруппированных по месяцам.
