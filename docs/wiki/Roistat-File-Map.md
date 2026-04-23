# Карта файлов Roistat

## Фронтенд

Основные страницы и вкладки:

- `frontend/src/pages/OverviewPage.tsx`.
- `frontend/src/components/OverviewTabs.tsx`.

Фильтры и состояния:

- `frontend/src/components/FilterPanel.tsx`.
- `frontend/src/hooks/useFilterOptions.ts`.
- `frontend/src/hooks/useReports.ts`.

Вкладки:

- `frontend/src/components/FunnelView.tsx`.
- `frontend/src/components/FunnelSummaryTable.tsx`.
- `frontend/src/components/TouchFunnelTable.tsx`.
- `frontend/src/components/SubscriptionsComparePanel.tsx`.
- `frontend/src/components/WeeklyTable.tsx`.
- `frontend/src/components/RawUsersTable.tsx`.
- `frontend/src/components/BreakdownTable.tsx`.

Диалоги и верхняя панель:

- `frontend/src/components/BotRegistryDialog.tsx`.
- `frontend/src/components/AdvertisingCompaniesDialog.tsx`.
- `frontend/src/components/BudgetDialog.tsx`.
- `frontend/src/components/AdMetricsDialog.tsx`.
- `frontend/src/components/SystemSettingsDialog.tsx`.
- `frontend/src/components/AccessManagerDialog.tsx`.

Авторизация:

- `frontend/src/App.tsx`.
- `frontend/src/hooks/useTelegramAuth.ts`.
- `frontend/src/hooks/useTelegramAccess.ts`.

## Бекенд API

Основные роутеры:

- `backend/app/api/routers/reports.py`.
- `backend/app/api/routers/admin.py`.
- `backend/app/api/routers/bots.py`.
- `backend/app/api/routers/advertising.py`.
- `backend/app/api/routers/budgets.py`.
- `backend/app/api/routers/ad_metrics.py`.
- `backend/app/api/routers/utm.py`.
- `backend/app/api/routers/auth.py`.

## Расчеты и сервисы

- `backend/app/services/report_repository.py`.
- `backend/app/services/report_cache_service.py`.
- `backend/app/services/raw_user_repository.py`.
- `backend/app/services/roistat_weekly_report.py`.
- `backend/app/services/weekly_reports.py`.

## Модели и таблицы

- `backend/app/models/analytics.py`.
- `raw_bot_users`.
- `agg_tg_subs_daily`.
- `telegram_subscription_events`.
- `budget_weekly`.
- `ad_metrics_weekly`.
- `advertising_companies`.

## Фоновые задачи

- `backend/app/worker/tasks.py`.
- `run_roistat_weekly_export_job()`.
- `schedule_ingestion_job()`.
- `schedule_google_sheets_job()`.

## Конфиг

- `backend/app/core/config.py`.
- Переменные `google_sheets_*`, `roistat_weekly_*`, `weekly_cache_ttl_seconds`.
