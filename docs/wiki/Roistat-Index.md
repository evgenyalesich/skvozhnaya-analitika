# Документация Roistat

В проекте есть отдельная "Roistat-часть":

- Экран с таблицей `Weekly` (UI).
- API-метод, который считает строки `Weekly` (`/api/reports/roistat-weekly`).
- Фоновая задача, которая экспортирует эти же строки в Google Sheets (`/api/admin/sync-roistat-weekly`).
- Telegram-аутентификация для доступа к дашборду.

## Источники данных

- Google Sheets:
  - Исходная вкладка: `'pokerhub_robot'!A:U` (только чтение, базовые метрики Weekly).
  - Целевая вкладка экспорта: `settings.roistat_weekly_sheet_title` (по умолчанию `Weekly`).
  - Вкладка-источник форматирования: `"Итоговые результаты студенты"` (нужна только для копирования форматирования и хедеров при экспорте).
- Postgres (analytics DB):
  - `raw_bot_users`: выбор когорты first_touch (`mode=first_touch`).
  - `budget_weekly`: плановый бюджет по неделям.
  - `ad_metrics_weekly`: фактический расход (spend) по неделям.
  - `agg_tg_subs_daily`: агрегированные подписки по дням, включая `saloon_subscribed`.
  - `telegram_subscription_events`: сырые события подписки (используется для салуна только в режиме когорты first_touch).
- Redis:
  - Кеш ответов `GET /api/reports/roistat-weekly` под ключами `reports:roistat_weekly:v2:*`.
  - Статусы фоновых задач под ключами `sync:last_roistat_weekly*`.
  - Локи под ключами `locks:*`.

## Основные потоки

UI (таб `Weekly`):

1. Фронт запрашивает `GET /api/reports/roistat-weekly`.
2. Бек собирает и склеивает:
   - базовые метрики из Google Sheets (`pokerhub_robot`)
   - `budget` из Postgres (`budget_weekly` или `ad_metrics_weekly`)
   - `saloon` из Postgres (`agg_tg_subs_daily` или `telegram_subscription_events`, зависит от режима когорты)
3. Результат кешируется в Redis и возвращается в UI.

Экспорт (Google Sheets):

1. Админ триггерит `POST /api/admin/sync-roistat-weekly` (опционально с `first_touch_*`).
2. Воркер запускает `run_roistat_weekly_export_job`, пересчитывает строки и пишет их в целевую вкладку.

## Страницы Wiki в этом каталоге

- `docs/wiki/Roistat-Weekly.md`: экран Weekly, API-контракт, логика метрик.
- `docs/wiki/Roistat-Export.md`: экспорт и админ-ручка.
- `docs/wiki/Roistat-Auth.md`: Telegram-аутентификация.
- `docs/wiki/Roistat-File-Map.md`: карта файлов (что где находится и зачем).
- `docs/wiki/Roistat-Troubleshooting.md`: диагностика типовых проблем.
