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

## Колонки таблицы

Воронка:

- `Вход`, `Собеседование`, `Прошел собес`, `Оффер`, `Наигрывают дистанцию`, `Контракт`.
- Все значения считаются как `COUNT(DISTINCT tg_user_id)` в `raw_bot_users`.
- `CR ...` считается относительно предыдущей стадии.

Рекламные метрики и бюджет:

- `Показы`, `Клики`, `Подписчик`, `Spend`, `Budget` берутся из `GET /api/reports/budgets/weekly` и агрегируются по `bot_key`.
- `CTR = clicks / impressions`.
- `CR Подписчик = subscribed / clicks`.
- `CPM = spend_base / impressions * 1000`.
- `CPC = spend_base / clicks`.
- `CPF = spend_base / subscribed`.
- `CPL = spend_base / lead`.
- `CPA = spend_base / platform`.
- `Цена контракта = spend_base / contract`.
- `% Done = spend / budget * 100`.
- `spend_base` для метрик равен `spend`, если `spend > 0`, иначе `budget`.
