# Вкладка TotalB

## Что показывает

- Таблица воронки по ботам.
- Дополнительные рекламные метрики и бюджеты.
- Понедельная детализация по боту.

## Файлы

- `frontend/src/components/FunnelSummaryTable.tsx`.
- `frontend/src/hooks/useFunnelSummary.ts`.
- `frontend/src/hooks/useBudgetWeeklyReport.ts`.
- `frontend/src/pages/OverviewPage.tsx`.

## API

- `GET /api/reports/funnel-start/summary?group_by=bot_key`.
- `GET /api/reports/budgets/weekly`.
- `GET /api/reports/weekly?group_by=bot&group_key=...`.

## Источники данных

- `raw_bot_users` для воронки.
- `budget_weekly` и `ad_metrics_weekly` для рекламных метрик.

## Особенности логики

- Вкладка показывает только боты, которые подходят под шаблон:
- `bot_key` начинается с `tgads` или заканчивается на `bot`.
- В список также попадают боты, которые есть в бюджете, даже если воронка пустая.

## Метрики в таблице

- Воронка считается по `raw_bot_users` аналогично вкладке Funnel.
- Рекламные метрики берутся из ответа `budgets/weekly` и агрегируются по `bot_key`.
- Часть метрик вычисляется на фронте.
- `CTR`, `CPC`, `CPM`, `CPF`, `CPL`, `CPA`, `contract_cost`, `% Done`.

## Кнопки и действия

- Сортировка по клику на заголовок колонки.
- `Скачать CSV` формирует CSV на фронте из текущих строк.
- Раскрытие строки показывает понедельную статистику.

## Понедельная статистика

- Источник: `GET /api/reports/weekly`.
- Данные берутся из Redis ключей `reports:weekly:*`.
- Если кэш не заполнен, таблица будет пустая.

## Колонки таблицы

Воронка:

- `Вход`, `Lead`, `Платформа`, `Обучение`, `Курс`, `Собеседование`, `Прошел собес`, `Оффер`, `Наигрывают дистанцию`, `Контракт`.
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
