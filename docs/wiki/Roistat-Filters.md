# Глобальные фильтры

Эта страница описывает общую панель фильтров, которая влияет на большинство вкладок.

## Где находится

Файлы:

- `frontend/src/components/FilterPanel.tsx`
- `frontend/src/hooks/useFilterOptions.ts`
- `frontend/src/hooks/useReports.ts`
- `backend/app/api/report_filters.py`

## Источники значений для селектов

- Список РК: `GET /api/advertising-companies`.
- UTM Source: `GET /api/utm/sources`.
- UTM Campaign: `GET /api/utm/campaigns`.
- UTM Medium: `GET /api/utm/mediums`.
- UTM Content: `GET /api/utm/contents`.
- UTM Term: `GET /api/utm/terms`.

Важно:

- UTM-значения собираются из таблицы `lead_resources` в каждом bot‑database.
- Для UTM запросов передается список баз, выбранных в фильтре `Базы`.

## Поведение

- Поля `Дата с` и `Дата по` применяются сразу без кнопки `ПРИМЕНИТЬ`.
- Остальные фильтры применяются после кнопки `ПРИМЕНИТЬ`.
- Кнопки `Все` и `Очистить` работают только для соответствующего мультиселекта.

## Какие параметры уходят в API

Логика сборки параметров находится в `buildFilterParams()`.

Список параметров:

- `start_date`.
- `end_date`.
- `bots`.
- `advertising_companies`.
- `utm_source`.
- `utm_campaign`.
- `utm_medium`.
- `utm_content`.
- `utm_term`.

## Куда применяются фильтры

Фильтры передаются в следующие методы:

- `GET /api/reports/funnel-start/total`.
- `GET /api/reports/funnel-start/daily`.
- `GET /api/reports/funnel-start/breakdown`.
- `GET /api/reports/funnel-start/stages`.
- `GET /api/reports/funnel-start/summary`.
- `GET /api/reports/funnel-start/raw`.
- `GET /api/reports/subscriptions/compare`.
- `GET /api/reports/touch/funnel-summary`.

Дополнительно:

- Вкладка `Weekly` использует `start_date/end_date` как `event_start/event_end`.

## Ограничения

- Бэк ограничивает диапазон `start_date..end_date` до 730 дней.
- Если диапазон больше, API вернет ошибку `400`.
