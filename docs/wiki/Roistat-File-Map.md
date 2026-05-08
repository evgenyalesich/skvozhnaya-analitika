# Карта файлов Roistat

## Frontend

### Точки входа

- `frontend/src/main.tsx`
- `frontend/src/App.tsx`
- `frontend/src/components/layout/OverviewPage.tsx`

### Layout и shell

- `frontend/src/components/layout/AppShell.tsx`
- `frontend/src/components/layout/Sidebar.tsx`
- `frontend/src/components/layout/Topbar.tsx`
- `frontend/src/components/layout/overviewFilterState.ts`
- `frontend/src/components/layout/overviewFilterChips.ts`

### Основные вкладки / компоненты

- `frontend/src/components/FunnelView.tsx`
- `frontend/src/components/FunnelSummaryTable.tsx`
- `frontend/src/components/FunnelTreeTable.tsx`
- `frontend/src/components/MainReportTable.tsx`
- `frontend/src/components/WeeklyTable.tsx`
- `frontend/src/components/RoistatWeeklyTreeTable.tsx`
- `frontend/src/components/RoistatLessonsTable.tsx`
- `frontend/src/components/SubscriptionsComparePanel.tsx`
- `frontend/src/components/RawUsersTable.tsx`
- `frontend/src/components/UserSearchPanel.tsx`
- `frontend/src/components/FaqPanel.tsx`

### Admin / settings dialogs

- `frontend/src/components/BotRegistryDialog.tsx`
- `frontend/src/components/AdvertisingCompaniesDialog.tsx`
- `frontend/src/components/BudgetDialog.tsx`
- `frontend/src/components/AdMetricsDialog.tsx`
- `frontend/src/components/SystemSettingsDialog.tsx`
- `frontend/src/components/AccessManagerDialog.tsx`
- `frontend/src/components/EmployeeRegistryDialog.tsx`

### Hooks

- `frontend/src/hooks/useReports.ts`
- `frontend/src/hooks/useMainReport.ts`
- `frontend/src/hooks/useRoistatWeekly.ts`
- `frontend/src/hooks/useRoistatWeeklyTree.ts`
- `frontend/src/hooks/useRoistatLessons.ts`
- `frontend/src/hooks/useRawUsers.ts`
- `frontend/src/hooks/useSubscriptionsCompare.ts`
- `frontend/src/hooks/useTouchSummary.ts`
- `frontend/src/hooks/useTouchFunnelSummary.ts`
- `frontend/src/hooks/useBudgets.ts`
- `frontend/src/hooks/useBudgetWeeklyReport.ts`
- `frontend/src/hooks/useAdMetrics.ts`
- `frontend/src/hooks/useFilterOptions.ts`
- `frontend/src/hooks/useTelegramAuth.ts`
- `frontend/src/hooks/useTelegramAccess.ts`

## Backend API

### Общие точки входа

- `backend/app/main.py`
- `backend/app/api/routes.py`
- `backend/app/api/dependencies.py`
- `backend/app/api/report_filters.py`

### Router groups

- `backend/app/api/routers/admin.py`
- `backend/app/api/routers/admin_parts/*`
- `backend/app/api/routers/reports.py`
- `backend/app/api/routers/reports_extras.py`
- `backend/app/api/routers/reports_funnel.py`
- `backend/app/api/routers/reports_funnel_parts/*`
- `backend/app/api/routers/reports_roistat.py`
- `backend/app/api/routers/reports_roistat_weekly.py`
- `backend/app/api/routers/reports_roistat_companies.py`
- `backend/app/api/routers/reports_roistat_companies_parts/*`
- `backend/app/api/routers/reports_roistat_lessons.py`
- `backend/app/api/routers/reports_roistat_tree.py`
- `backend/app/api/routers/advertising.py`
- `backend/app/api/routers/bots.py`
- `backend/app/api/routers/budgets.py`
- `backend/app/api/routers/ad_metrics.py`
- `backend/app/api/routers/auth.py`
- `backend/app/api/routers/telegram.py`
- `backend/app/api/routers/utm.py`

## Сервисы и расчёты

### Базовые SQL-репозитории

- `backend/app/services/report_repository.py`
- `backend/app/services/report_repository_touch.py`
- `backend/app/services/report_repository_budget.py`
- `backend/app/services/report_repository_funnel_summary*.py`
- `backend/app/services/report_repository_subscriptions*.py`
- `backend/app/services/raw_user_repository.py`

### Кэш и orchestration

- `backend/app/services/report_cache_service.py`
- `backend/app/services/main_report_cache_warmer.py`

### Weekly / Roistat

- `backend/app/services/roistat_weekly_report.py` — facade
- `backend/app/services/roistat_weekly_parts/roistat_weekly_report.py`
- `backend/app/services/roistat_weekly_parts/roistat_weekly_report_impl.py`
- `backend/app/services/roistat_weekly_parts/roistat_weekly_report_core.py`
- `backend/app/services/roistat_weekly_parts/roistat_weekly_report_data_*`

### Aggregation / attribution

- `backend/app/services/attribution_service.py`
- `backend/app/services/aggregate_refresher.py`
- `backend/app/services/aggregate_refresher_rebuild.py`
- `backend/app/services/aggregate_refresher_cache.py`

### Telegram / access / settings

- `backend/app/services/telegram_auth.py`
- `backend/app/services/telegram_access_service.py`
- `backend/app/services/telegram_membership_parts/*`
- `backend/app/services/system_settings_service.py`
- `backend/app/services/employee_registry_service.py`

## Ingestion и фоновые процессы

### Ingestion

- `backend/app/ingestion/ingestion_service.py`
- `backend/app/ingestion/google_sheets_ingestor*.py`
- `backend/app/ingestion/pokerhub_ingestor*.py`
- `backend/app/ingestion/lead_ingestor.py`
- `backend/app/ingestion/telegram_ingestor.py`

### Replication

- `backend/app/ingestion/replication_worker.py`
- `backend/app/ingestion/replication_worker_manager.py`
- `backend/app/ingestion/replication_stream/*`

### Workers / scheduler

- `backend/app/worker/tasks.py`
- `backend/app/worker/runtime/*`
- `backend/app/core/periodic_sync.py`

## Модели / таблицы

Описаны в одном месте:

- `backend/app/models/analytics.py`

Главные таблицы:

- `raw_bot_users`
- `ph_user_mirror_replica`
- `agg_daily_new_users`
- `agg_tg_subs_daily`
- `agg_weekly_funnel_bot`
- `agg_weekly_funnel_company`
- `telegram_subscription_events`
- `telegram_chat_memberships`
- `telegram_chat_totals`
- `budget_weekly`
- `ad_metrics_weekly`
- `system_settings`
- `sync_event_logs`
- `replication_dlq`
