# Диагностика Roistat

## Weekly показывает старые цифры

`GET /api/reports/roistat-weekly` кешируется в Redis.

Очистка ключей:

```bash
redis-cli --scan --pattern 'reports:roistat_weekly:v2:*' | xargs -r redis-cli del
```

Если Redis не на localhost, добавь `-h/-p/-a` к обоим вызовам `redis-cli`.

## Салун всегда 0

Это нормально в таких случаях:

- Не задан `TELEGRAM_COMMUNITY_ID`.
- В `agg_tg_subs_daily` нет строк за нужный диапазон (агрегация не запускалась или окно пересчета маленькое).
- Включен first_touch, но в `telegram_subscription_events` нет событий subscribed для этой когорты.

Проверочные запросы:

```sql
SELECT COUNT(*) FROM agg_tg_subs_daily WHERE saloon_subscribed > 0;
SELECT COUNT(*) FROM telegram_subscription_events WHERE status='subscribed';
```

## Weekly пустой

`RoistatWeeklyReport` вернет пусто, если не хватает конфигурации:

- `google_sheets_credentials_path`
- `roistat_weekly_sheet_id` или `google_sheets_spreadsheet_id`

Экспорт в таком случае тоже упадет.

## Экспорт не стартует

Воркеры используют лок `locks:roistat_weekly`.

Если предыдущая задача упала, лок может жить до истечения TTL.

Проверка:

```bash
redis-cli get locks:roistat_weekly
```

## Экспорт пишет не те колонки

Расчет использует фиксированные индексы колонок в `'pokerhub_robot'!A:U`.

Если source sheet поменялся, править:

- `backend/app/services/roistat_weekly_report.py`:
  - `start_dt` из `row[4]` (E)
  - `platform_dt` из `row[17]` (R)
  - `learning_dt` из `row[18]` (S)
  - `group_value` из `row[19]` (T)
  - `courses_value` из `row[20]` (U)
