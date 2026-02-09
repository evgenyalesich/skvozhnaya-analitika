# Roistat: экраны и элементы управления

Документ описывает каждый экран, вкладку и кнопку дашборда Roistat. Для каждого элемента указано, откуда берутся данные и какая логика применяется.

## Авторизация

Экран входа появляется, пока нет токена доступа.

Файлы:

- `frontend/src/App.tsx`
- `frontend/src/hooks/useTelegramAuth.ts`
- `backend/app/api/routers/auth.py`
- `backend/app/api/routers/telegram.py`

Кнопки и логика:

- `Войти`.
- Вызывает `POST /api/auth/telegram/start`, получает `start_token` и `login_url`.
- Открывает диалог с кнопкой перехода в Telegram.
- Каждые 2 секунды опрашивает `GET /api/auth/telegram/status?token=...`.
- При `status=ok` сохраняет `access_token` в `localStorage` и добавляет `Authorization: Bearer ...` ко всем запросам.

Примечание:

- Доступ к админ-методам зависит от Telegram-ACL. Управляется в разделе `Доступы`.

## Главный экран Analytics Dashboard

Точка входа:

- `frontend/src/pages/OverviewPage.tsx`

### Верхняя панель действий

Кнопки и действия:

- `Обновить список баз`.
- Вызывает `GET /api/bots` через `useBotRegistry`.
- Используется для актуализации списка баз и их отображаемых названий.

- `Настроить базы`.
- Открывает `BotRegistryDialog`.
- Сохранение вызывает `POST /api/bots/registry` для каждого элемента.
- Важно: это не создает новые БД, а управляет отображением и активностью в UI.

- `Настроить РК`.
- Открывает `AdvertisingCompaniesDialog`.
- Сохранение вызывает `POST /api/advertising-companies` и пересчет привязок РК.
- На бэке запускается `AdvertisingCompanyService.rebuild_assignments()` и `AttributionService.rebuild_in_session()`.

- `Бюджеты`.
- Открывает `BudgetDialog`.
- CRUD через `GET/POST/PUT/DELETE /api/budgets`.
- При создании/обновлении бюджет автоматически пишет `spend` в `ad_metrics_weekly`.

- `Рекламные метрики`.
- Открывает `AdMetricsDialog`.
- CRUD через `GET/POST/PUT/DELETE /api/ad-metrics`.

- `Настройки обновлений`.
- Открывает `SystemSettingsDialog`.
- `GET /api/admin/settings`, `PUT /api/admin/settings`.
- Логи: `GET /api/admin/sync-logs`.
- Кнопки действий:
- `Синх сейчас` -> `POST /api/admin/sync-all`.
- `Синх SM` -> `POST /api/admin/sync-google-sheets`.
- `Пересчитать РК` -> `POST /api/advertising-companies/rebuild`.

- `Доступы`.
- Открывает `AccessManagerDialog`.
- `GET /api/admin/telegram-access`, `POST /api/admin/telegram-access`, `DELETE /api/admin/telegram-access/{tg_user_id}`.
- Требуется `Authorization: Bearer ...`.

### Статусы обновлений

Выводятся справа вверху, обновляются каждые 30 секунд.

Источники:

- `GET /api/admin/sync-status`.
- Поля `last_ingestion`, `last_sm`, `last_ingestion_success`.

### Панель фильтров

Файл:

- `frontend/src/components/FilterPanel.tsx`

Данные для селектов:

- `GET /api/advertising-companies`.
- `GET /api/utm/sources`.
- `GET /api/utm/campaigns`.
- `GET /api/utm/mediums`.
- `GET /api/utm/contents`.
- `GET /api/utm/terms`.

Особенности логики:

- Поля `Дата с` и `Дата по` применяются автоматически без кнопки `ПРИМЕНИТЬ`.
- Остальные фильтры применяются только после нажатия `ПРИМЕНИТЬ`.
- Кнопки `Все` и `Очистить` меняют содержимое мультиселекта.

Параметры запросов:

- Формируются в `frontend/src/hooks/useReports.ts` функцией `buildFilterParams()`.

## Вкладки дашборда

Файл с логикой переключения:

- `frontend/src/components/OverviewTabs.tsx`

### Overview

Что показывает:

- Карточки `Users at Funnel Start`, `Total Budget`, `CAC`.
- График `Daily New Users` с выбором периода.
- Таблица `Breakdown`.

Источники:

- `GET /api/reports/funnel-start/total`.
- `GET /api/reports/funnel-start/daily`.
- `GET /api/reports/funnel-start/breakdown`.

Кнопки и логика:

- Переключатели периода `7 дней`, `14 дней`, `Месяц`, `Все время`.
- Поле `Дата по` меняет конец периода для графика.

### Funnel

Что показывает:

- Воронка конверсий и таблица стадий.

Источники:

- `GET /api/reports/funnel-start/stages`.

### TotalB

Что показывает:

- Таблица `TotalB: Воронка по ботам`.
- Строки агрегируются по `bot_key`.
- Метрики бюджета и рекламные метрики подтягиваются из недельных агрегатов.

Источники:

- `GET /api/reports/funnel-start/summary?group_by=bot_key`.
- `GET /api/reports/budgets/weekly` для дополнительных рекламных метрик.

Кнопки и логика:

- Сортировка по клику на заголовки колонок.
- `Скачать CSV`.
- Раскрытие строки показывает понедельную статистику:
- `GET /api/reports/weekly?group_by=bot&group_key=...`.

### TotalA

Что показывает:

- Таблица `TotalA: Воронка по РК`.
- Строки агрегируются по `advertising_company`.
- Показаны привязанные боты для каждой РК.

Источники:

- `GET /api/reports/funnel-start/summary?group_by=advertising_company`.
- `GET /api/advertising-companies` для списка РК и привязок.
- `GET /api/reports/budgets/weekly` для доп. метрик.

Кнопки и логика:

- `Скачать CSV`.
- Раскрытие строки показывает понедельную статистику:
- `GET /api/reports/weekly?group_by=company&group_key=...`.

### TotalC

Что показывает:

- Воронка в разрезе `FIRST TOUCH` и `LAST TOUCH`.
- Метрики бюджета подмешиваются по bot_key.

Источники:

- `GET /api/reports/touch/funnel-summary?mode=first|last`.
- `GET /api/reports/budgets/weekly`.

Кнопки и логика:

- Переключатель `FIRST TOUCH` и `LAST TOUCH`.
- `Скачать CSV`.
- Раскрытие строки показывает понедельную статистику:
- `GET /api/reports/touch/weekly?group_key=...&mode=first|last`.

### TG SUBS

Что показывает:

- Сравнение стартов и подписок по каналам и салуну.
- Таблица и бар‑чарт.

Источники:

- `GET /api/reports/subscriptions/compare`.

Кнопки и логика:

- `Интервал`: `По дням` или `По неделям`.
- При `По неделям` доступен фильтр `Месяц`.
- Чекбоксы управляют видимостью метрик в таблице и графике.
- Раскрытие строки РК показывает боты, раскрытие бота показывает строки по датам.

Примечания:

- Бек использует `TELEGRAM_CHANNEL_ID` и `TELEGRAM_COMMUNITY_ID`.
- Если даты не заданы, бэк применяет дефолтный диапазон `settings.subscriptions_compare_default_days`.

### Weekly

Что показывает:

- Еженедельный отчет Roistat и итог по месяцам.

Источники:

- `GET /api/reports/roistat-weekly`.

Кнопки и логика:

- Тумблер `Фильтр first_touch`.
- Дропдаун `Месяц`.
- Подробная логика описана в `Roistat-Weekly.md`.

### RAW Users

Что показывает:

- Сырые записи пользователей по фильтрам.

Источники:

- `GET /api/reports/funnel-start/raw`.

Кнопки и логика:

- `Обновить` вручную перезапрашивает все данные вкладки.
- `Экспорт CSV` вызывает `GET /api/reports/funnel-start/export` с текущими фильтрами.
- Сортировка по колонкам.
- Пагинация и смена размера страницы.
- Фильтры в шапке таблицы применяются сразу.

### RAW UTM

Что показывает:

- Breakdown по UTM/кампаниям.

Источники:

- `GET /api/reports/funnel-start/breakdown`.

Кнопки и логика:

- Кнопки `utm_source`, `utm_campaign`, `source_campaign`, `advertising_company` меняют `group_by`.

## Где смотреть логику на бэке

Ключевые файлы:

- `backend/app/api/routers/reports.py`.
- `backend/app/services/report_cache_service.py`.
- `backend/app/services/report_repository.py`.
- `backend/app/services/roistat_weekly_report.py`.
- `backend/app/services/weekly_reports.py`.

## Где смотреть логику на фронте

Ключевые файлы:

- `frontend/src/pages/OverviewPage.tsx`.
- `frontend/src/components/*`.
- `frontend/src/hooks/*`.
