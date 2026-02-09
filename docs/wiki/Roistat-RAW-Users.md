# Вкладка RAW Users

## Что показывает

- Сырые записи пользователей с расширенными фильтрами.

## Файлы

- `frontend/src/components/RawUsersTable.tsx`.
- `frontend/src/hooks/useReports.ts`.
- `backend/app/services/raw_user_repository.py`.

## API

- `GET /api/reports/funnel-start/raw`.
- `GET /api/reports/funnel-start/export`.

## Источник данных

- Таблица `raw_bot_users`.

## Фильтры и параметры

Глобальные фильтры:

- Применяются через `ReportFilters`.

Колонки‑фильтры:

- Передаются как `raw_*` параметры.
- Логика описана в `backend/app/api/report_filters.py` и `raw_user_repository.py`.

## Сортировка

- Разрешенные поля: `created_at`, `tg_user_id`, `bot_key`, `budget`, `utm_source`, `utm_campaign`, `utm_medium`, `utm_content`, `utm_term`, `advertising_company`, `ingested_at`.
- Остальные поля не сортируются.

## Поле Бюджет

- Это не `raw_bot_users.budget`.
- Значение считается как `budget_weekly / learning` для соответствующего дня и кампании.
- Расчет выполняется только если `started_learning = true`.
- Если соответствия нет, выводится `0.00`.

## Кнопки

- `Обновить` повторно запрашивает все данные вкладки.
- `Экспорт CSV` генерирует CSV на бэке с учетом текущих фильтров.

## Особенности

- `First Touch` и `Last Touch` считаются наличием меток, отличных от `NULL`, пустой строки и `нет метки`.
- Статусы собеседования и оффера фильтруются через `ILIKE`.
