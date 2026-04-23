# Экспорт Roistat Weekly (Google Sheets)

Цель: записать те же строки `Weekly` в Google Sheets (вкладка, используемая снаружи).

## Как триггерится

Вручную (admin API):

- `POST /api/admin/sync-roistat-weekly`
- Опциональные параметры:
  - `first_touch_start=YYYY-MM-DD`
  - `first_touch_end=YYYY-MM-DD`

Реализация в воркере:

- `backend/app/worker/tasks.py`
  - `schedule_roistat_weekly_export_job()`
  - `run_roistat_weekly_export_job()`

## Настройки и env

Google Sheets:

- `settings.google_sheets_credentials_path` (service account JSON)
- `settings.roistat_weekly_sheet_id` (опционально)
  - если не задан, берется `settings.google_sheets_spreadsheet_id`
- `settings.roistat_weekly_sheet_title` (по умолчанию `Weekly`)

## Что именно пишется

Экспорт:

1. Читает 2 строки хедеров из вкладки `"Итоговые результаты студенты"`:
   - `RoistatWeeklyReport.load_source_headers()`
2. Считает строки:
   - `RoistatWeeklyReport.build_weekly_rows()`
3. Пишет в целевую вкладку (`roistat_weekly_sheet_title`):
   - очищает диапазон `A1:Z`
   - пишет значения, начиная с `A1`
4. Копирует форматирование из вкладки-источника и выставляет числовой формат для колонки бюджета.

Реализация:

- `backend/app/services/roistat_weekly_report.py::export_to_sheet()`
- `backend/app/services/roistat_weekly_report.py::_copy_source_formatting()`

## Локи и статусы

Лок:

- Redis key: `locks:roistat_weekly`
- Используется и для enqueue (`queued`), и во время выполнения (`running`).

Статусы:

- `sync:last_roistat_weekly`
- `sync:last_roistat_weekly_success`

Payload статуса:

- `ts`
- `status`: `ok` или `error`
- `error` (если было)
- `first_touch_start`, `first_touch_end` (эхо параметров)

## Операционные команды

Дернуть экспорт:

```bash
curl -X POST "${API_BASE}/api/admin/sync-roistat-weekly?first_touch_start=2026-02-01&first_touch_end=2026-02-29"   -H "Authorization: Bearer ${TOKEN}"
```

Проверить статусы:

```bash
curl "${API_BASE}/api/admin/sync-status" -H "Authorization: Bearer ${TOKEN}"
```

## Типовые причины падений

- Нет Google credentials или spreadsheet id:
  - API вернет пусто, экспорт упадет исключением.
- Экспорт долго выполняется:
  - TTL лока в `tasks.py` - 1800 секунд. Если задача зависнет дольше, лок может протухнуть и позволит запустить вторую задачу.
- Поменялась структура Google Sheets:
  - В `RoistatWeeklyReport` индексы колонок и имена вкладок частично захардкожены.
