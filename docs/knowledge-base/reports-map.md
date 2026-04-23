# Reports Map

## Вкладки UI

Вкладки overview-экрана объявлены здесь:
- [OverviewPage.tsx](/home/fervuld/prod/analytic-system/frontend/src/pages/OverviewPage.tsx:111)

Сейчас в UI есть:
- `overview`
- `totalb`
- `main`
- `tgsubs`
- `lessons`
- `raw`
- `usersearch`
- `faq`

## Основные отчёты и endpoints

Список endpoints:
- [reports.py](/home/fervuld/prod/analytic-system/backend/app/api/routers/reports.py:191)

### 1. Funnel Start

Подробная wiki по вкладке:
- [tab-bots.md](/home/fervuld/prod/analytic-system/docs/knowledge-base/tab-bots.md)

Endpoints:
- `/api/reports/funnel-start/total`
- `/api/reports/funnel-start/daily`
- `/api/reports/funnel-start/breakdown`
- `/api/reports/funnel-start/conversions`
- `/api/reports/funnel-start/stages`
- `/api/reports/funnel-start/summary`
- `/api/reports/funnel-start/tree`
- `/api/reports/funnel-start/raw`
- `/api/reports/funnel-start/export`

UI hook:
- [useReports.ts](/home/fervuld/prod/analytic-system/frontend/src/hooks/useReports.ts:283)

Где считается:
- [report_cache_service.py](/home/fervuld/prod/analytic-system/backend/app/services/report_cache_service.py:15)
- [report_repository.py](/home/fervuld/prod/analytic-system/backend/app/services/report_repository.py:473)

### 2. Weekly / Main Report

Подробная wiki по вкладке:
- [tab-main-report.md](/home/fervuld/prod/analytic-system/docs/knowledge-base/tab-main-report.md)

Endpoints:
- `/api/reports/weekly`
- `/api/reports/weekly-filtered`
- `/api/reports/roistat-weekly`
- `/api/reports/roistat-weekly/companies-weekly`
- `/api/reports/roistat-weekly/tree`

UI hooks:
- [useRoistatWeekly.ts](/home/fervuld/prod/analytic-system/frontend/src/hooks/useRoistatWeekly.ts:1)
- [useMainReport.ts](/home/fervuld/prod/analytic-system/frontend/src/hooks/useMainReport.ts:1)

Главный endpoint основного отчёта:
- [reports.py](/home/fervuld/prod/analytic-system/backend/app/api/routers/reports.py:624)

Что возвращает main report:
- `rows` — строки по рекламным кабинетам/компаниям
- `bot_rows` — строки по ботам
- `week_totals` — недельные итоги

### 3. Roistat Lessons

Подробная wiki по вкладке:
- [tab-pokerhub-lessons.md](/home/fervuld/prod/analytic-system/docs/knowledge-base/tab-pokerhub-lessons.md)

Endpoint:
- `/api/reports/roistat-lessons`

UI hook:
- [useRoistatLessons.ts](/home/fervuld/prod/analytic-system/frontend/src/hooks/useRoistatLessons.ts:1)

Router:
- [reports.py](/home/fervuld/prod/analytic-system/backend/app/api/routers/reports.py:2531)

Смысл:
- матрица прохождения уроков PokerHub по пользователям и курсам.

### 4. Raw Users

Подробная wiki по вкладке:
- [tab-raw-users.md](/home/fervuld/prod/analytic-system/docs/knowledge-base/tab-raw-users.md)

Endpoints:
- `/api/reports/funnel-start/raw`
- `/api/reports/funnel-start/export`

UI hook:
- [useRawUsers.ts](/home/fervuld/prod/analytic-system/frontend/src/hooks/useRawUsers.ts:1)

Repository:
- [raw_user_repository.py](/home/fervuld/prod/analytic-system/backend/app/services/raw_user_repository.py:1)

### 4. Subscriptions Compare

Endpoint:
- `/api/reports/subscriptions/compare`

Router:
- [reports.py](/home/fervuld/prod/analytic-system/backend/app/api/routers/reports.py:2607)

Где считается:
- [report_cache_service.py](/home/fervuld/prod/analytic-system/backend/app/services/report_cache_service.py:83)
- [report_repository.py](/home/fervuld/prod/analytic-system/backend/app/services/report_repository.py:976)

Смысл:
- сравнение стартов ботов против подписок/отписок по дню или неделе.

### 5. Touch Attribution

Endpoints:
- `/api/reports/touch/summary`
- `/api/reports/touch/funnel-summary`
- `/api/reports/touch/weekly`

Где считается:
- [report_repository.py](/home/fervuld/prod/analytic-system/backend/app/services/report_repository.py:2120)

Режимы:
- `first`
- `last`

Отдельно в main/funnel используется семантика:
- `event`
- `first_touch`
- `last_touch`

### 6. Budget Weekly

Endpoint:
- `/api/reports/budgets/weekly`

Где считается:
- [report_repository.py](/home/fervuld/prod/analytic-system/backend/app/services/report_repository.py:2315)

Смысл:
- свод бюджета, рекламных метрик, стартов, стадий, подписок и course mix.
