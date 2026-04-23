# Документация Roistat

Эта вики описывает все экраны дашборда, источники данных и логику расчетов.

## Навигация

- Карта экранов: `Roistat-Screens`.
- Глобальные фильтры: `Roistat-Filters`.
- Верхняя панель и диалоги: `Roistat-Header-Actions`.
- Общие правила: `Roistat-Common-Rules`.
- Кэш и обновления: `Roistat-Cache-and-Refresh`.
- Экспорт Weekly: `Roistat-Export`.
- Авторизация: `Roistat-Auth`.
- Карта файлов: `Roistat-File-Map`.
- Диагностика: `Roistat-Troubleshooting`.

## Основные источники данных

- Postgres (analytics DB):
- `raw_bot_users`.
- `agg_tg_subs_daily`.
- `telegram_subscription_events`.
- `budget_weekly`.
- `ad_metrics_weekly`.
- `advertising_companies`.

- Google Sheets:
- `'pokerhub_robot'!A:U` для Weekly.
- Вкладка экспорта `Weekly`.

- Redis:
- Кеш `reports:*`.
- Статусы синков `sync:*`.
- Локи `locks:*`.

## Общая схема

- UI использует `OverviewPage` и набор хуков.
- Бэк отвечает через `api/routers/reports.py` и `api/routers/admin.py`.
- Расчеты выполняются в `ReportRepository`, `ReportCacheService`, `RoistatWeeklyReport`.

## Где описаны вкладки

- `Overview`: `Roistat-Overview`.
- `Funnel`: `Roistat-Funnel`.
- `TotalB`: `Roistat-TotalB`.
- `TotalA`: `Roistat-TotalA`.
- `TotalC`: `Roistat-TotalC`.
- `TG SUBS`: `Roistat-TG-Subs`.
- `Weekly`: `Roistat-Weekly`.
- `RAW Users`: `Roistat-RAW-Users`.
- `RAW UTM`: `Roistat-RAW-UTM`.
