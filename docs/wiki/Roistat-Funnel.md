# Вкладка Funnel

## Что показывает

- График воронки конверсий.
- Таблица по стадиям.

## Файлы

- `frontend/src/components/FunnelView.tsx`.
- `frontend/src/hooks/useReports.ts`.

## API

- `GET /api/reports/funnel-start/stages`.

## Источник данных

- Таблица `raw_bot_users`.

## Логика стадий

Все значения считаются как `COUNT(DISTINCT tg_user_id)` с фильтрами:

- `entered`: все пользователи.
- `lead`: `converted_to_lead = true`.
- `platform`: `registered_platform = true`.
- `learning`: `started_learning = true`.
- `course`: `completed_course = true`.
- `interview`: `interview_reached = true`.
- `passed`: `interview_passed = true`.
- `offer`: `offer_received = true`.
- `distance_grinding`: `distance_grinding = true`.
- `contract`: `contract_signed = true`.

## Примечания

- Проценты считаются на фронте.
- Фильтры из панели сверху влияют на выборку.

## Колонки таблицы

- `Шаг воронки`: название стадии.
- `Пользователей`: количество уникальных `tg_user_id` на стадии.
- `Процент от входа`: `stage / entered`.
- `CR от предыдущего`: `stage / предыдущая стадия`.
- `Отток от предыдущего`: `100% - CR от предыдущего`.
