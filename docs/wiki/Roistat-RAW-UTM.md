# Вкладка RAW UTM

## Что показывает

- Разбивку пользователей по UTM или рекламным компаниям.

## Файлы

- `frontend/src/components/BreakdownTable.tsx`.
- `frontend/src/pages/OverviewPage.tsx`.
- `backend/app/services/report_repository.py`.

## API

- `GET /api/reports/funnel-start/breakdown`.

## Источник данных

- Таблица `raw_bot_users`.

## Группировки

- `utm_source`.
- `utm_campaign`.
- `source_campaign`.
- `advertising_company`.

## Логика

- `source_campaign` формируется как `utm_source / utm_campaign`.
- Сортировка по количеству пользователей, лимит 20.
- Эта группировка также влияет на блок `Breakdown` во вкладке Overview.
