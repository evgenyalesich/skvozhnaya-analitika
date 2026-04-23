# Analytics Knowledge Base

Эта папка — заготовка под будущую Wiki/Gitea-базу знаний по `fin.zs-app.ru`.

Цель:
- быстро объяснить, откуда берётся каждая цифра;
- связать экран -> API -> сервис -> таблицы/поля;
- зафиксировать спорные места семантики перед созвоном.

## Что смотреть сначала

1. [reports-map.md](/home/fervuld/prod/analytic-system/docs/knowledge-base/reports-map.md)
2. [filters-and-semantics.md](/home/fervuld/prod/analytic-system/docs/knowledge-base/filters-and-semantics.md)
3. [formulas-and-kpi.md](/home/fervuld/prod/analytic-system/docs/knowledge-base/formulas-and-kpi.md)
4. [tab-bots.md](/home/fervuld/prod/analytic-system/docs/knowledge-base/tab-bots.md)
5. [tab-main-report.md](/home/fervuld/prod/analytic-system/docs/knowledge-base/tab-main-report.md)
6. [tab-pokerhub-lessons.md](/home/fervuld/prod/analytic-system/docs/knowledge-base/tab-pokerhub-lessons.md)
7. [tab-raw-users.md](/home/fervuld/prod/analytic-system/docs/knowledge-base/tab-raw-users.md)

## Страницы под созвон

Для предметного разбора вкладок:
- [BOTs](/home/fervuld/prod/analytic-system/docs/knowledge-base/tab-bots.md)
- [Основной отчет](/home/fervuld/prod/analytic-system/docs/knowledge-base/tab-main-report.md)
- [pokerhub_lessons](/home/fervuld/prod/analytic-system/docs/knowledge-base/tab-pokerhub-lessons.md)
- [raw users](/home/fervuld/prod/analytic-system/docs/knowledge-base/tab-raw-users.md)

## Главный вывод перед разбором

Живые отчёты считаются в основном из `raw_bot_users`, а не из старого weekly aggregate.
Это прямо зафиксировано в коде:
- [report_repository.py](/home/fervuld/prod/analytic-system/backend/app/services/report_repository.py:28)

Там `_can_use_weekly_bot_agg(...)` всегда возвращает `False`, потому что старый агрегат использует "старую семантику" и может расходиться с текущими экранами.

## Базовые источники данных

- `raw_bot_users` — главная таблица для большинства витрин.
- `telegram_subscription_events` — подписки/отписки.
- `tg_subs_daily_agg` — агрегат для compare subscriptions vs starts.
- `budget_weekly` — бюджеты.
- `ad_metrics_weekly` — рекламные метрики.
- `employee_registry` — пользователи, которых нужно исключать из отчётов.

## UI точка входа

Основной экран:
- [OverviewPage.tsx](/home/fervuld/prod/analytic-system/frontend/src/pages/OverviewPage.tsx:1)

Ключевой backend router:
- [reports.py](/home/fervuld/prod/analytic-system/backend/app/api/routers/reports.py:191)
