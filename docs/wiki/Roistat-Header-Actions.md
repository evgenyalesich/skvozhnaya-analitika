# Верхняя панель: кнопки и диалоги

Эта страница описывает кнопки над фильтрами и связанные диалоги.

## Где находится

Файлы:

- `frontend/src/pages/OverviewPage.tsx`
- `frontend/src/components/BotRegistryDialog.tsx`
- `frontend/src/components/AdvertisingCompaniesDialog.tsx`
- `frontend/src/components/BudgetDialog.tsx`
- `frontend/src/components/AdMetricsDialog.tsx`
- `frontend/src/components/SystemSettingsDialog.tsx`
- `frontend/src/components/AccessManagerDialog.tsx`

## Обновить список баз

- Запрос: `GET /api/bots`.
- Источник: список bot‑databases из Postgres + настройки из таблицы `bot_registry`.
- Используется для актуализации списка `Базы` в фильтре.

## Настроить базы

Диалог `Управление базами`.

- Сохранение: `POST /api/bots/registry`.
- Поля: `bot_key`, `display_name`, `is_active`.
- Важно: это только UI‑настройки, новые БД не создаются.

## Настроить РК

Диалог `Управление рекламными компаниями`.

- Сохранение: `POST /api/advertising-companies`.
- После сохранения бэк пересчитывает привязки РК к пользователям.
- Источник РК используется в фильтре `Компания` и вкладках `TotalA`, `TG SUBS`.

## Бюджеты

Диалог `Недельные бюджеты`.

- Чтение: `GET /api/budgets`.
- Создание: `POST /api/budgets`.
- Обновление: `PUT /api/budgets/{id}`.
- Удаление: `DELETE /api/budgets/{id}`.

Логика добавления диапазона:

- Для диапазона дат создается строка бюджета на каждую неделю.
- На бэке `week_start` приводится к понедельнику.
- При создании или обновлении бюджета автоматически апдейтим `spend` в `ad_metrics_weekly`.

## Рекламные метрики

Диалог `Недельные рекламные метрики`.

- Чтение: `GET /api/ad-metrics`.
- Создание: `POST /api/ad-metrics`.
- Обновление: `PUT /api/ad-metrics/{id}`.
- Удаление: `DELETE /api/ad-metrics/{id}`.

Логика добавления диапазона:

- Для диапазона дат создается строка метрик на каждую неделю.
- `week_start` приводится к понедельнику.

## Настройки обновлений

Диалог `Настройки обновлений и логи`.

- Чтение: `GET /api/admin/settings`.
- Сохранение: `PUT /api/admin/settings`.
- Логи: `GET /api/admin/sync-logs`.

Кнопки:

- `Синх сейчас` -> `POST /api/admin/sync-all`.
- `Синх SM` -> `POST /api/admin/sync-google-sheets`.
- `Пересчитать РК` -> `POST /api/advertising-companies/rebuild`.

## Доступы

Диалог `Управление доступом`.

- Чтение: `GET /api/admin/telegram-access`.
- Выдать: `POST /api/admin/telegram-access`.
- Отозвать: `DELETE /api/admin/telegram-access/{tg_user_id}`.

Важно:

- Все методы требуют `Authorization: Bearer <token>`.

## Статусы обновлений

Отображаются справа вверху.

- Запрос: `GET /api/admin/sync-status`.
- Поля: `last_ingestion`, `last_sm`, `last_ingestion_success`.
- Автообновление каждые 30 секунд.
