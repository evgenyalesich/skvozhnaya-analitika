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

## Колонки таблицы

- `ID`: `raw_bot_users.id`.
- `База`: `raw_bot_users.bot_key`.
- `TG ID`: `raw_bot_users.tg_user_id`.
- `Дата регистрации`: `raw_bot_users.created_at`.
- `User Block`: `raw_bot_users.user_block`.
- `UTM Source`: `raw_bot_users.utm_source`.
- `UTM Campaign`: `raw_bot_users.utm_campaign`.
- `First Touch Bot`: `raw_bot_users.first_touch_bot`.
- `First Touch Campaign`: `raw_bot_users.first_touch_campaign`.
- `Last Touch Bot`: `raw_bot_users.last_touch_bot`.
- `Last Touch Campaign`: `raw_bot_users.last_touch_campaign`.
- `UTM Medium`: `raw_bot_users.utm_medium`.
- `UTM Content`: `raw_bot_users.utm_content`.
- `UTM Term`: `raw_bot_users.utm_term`.
- `Компания`: `raw_bot_users.advertising_company`.
- `Бюджет`: вычисляемый бюджет на пользователя по `budget_weekly` и количеству `started_learning`.
- `Загружено`: `raw_bot_users.ingested_at`.
- `Lead`: `raw_bot_users.converted_to_lead`.
- `Платформа`: `raw_bot_users.registered_platform`.
- `Начал обучение`: `raw_bot_users.started_learning`.
- `Прошел курс`: `raw_bot_users.completed_course`.
- `Дошел до собеседования`: `raw_bot_users.interview_reached`.
- `Статус собеседования`: `raw_bot_users.interview_reached_status`.
- `Прошел собеседование`: `raw_bot_users.interview_passed`.
- `Статус прохождения`: `raw_bot_users.interview_passed_status`.
- `Оффер`: `raw_bot_users.offer_received`.
- `Статус оффера`: `raw_bot_users.offer_received_status`.
- `Контракт`: `raw_bot_users.contract_signed`.
- `Статус контракта`: `raw_bot_users.contract_signed_status`.
- `Наигрывают дистанцию`: `raw_bot_users.distance_grinding`.
- `Канал`: `raw_bot_users.channel_subscribed`.
- `Салун`: `raw_bot_users.community_member`.
- `Статус салуна`: `raw_bot_users.community_member_status`.
- `Команда`: `raw_bot_users.team_member`.
- `Внутренний статус`: `raw_bot_users.internal_status`.

## Бизнес-правила

- Все булевы фильтры работают в режиме `Все / ✓ / ✗`.
- Фильтры по статусам применяют `ILIKE` и ищут подстроку.
- `TG ID` фильтруется по подстроке, приводится к строке на бэке.
- `First Touch` и `Last Touch` проверяют наличие метки, исключая `NULL`, пустую строку и `нет метки`.
