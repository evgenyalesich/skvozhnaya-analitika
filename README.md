# Сквозная аналитика PokerHub — полная документация

Этот документ описывает, **что именно реализовано**, **как устроен сбор**, **как считаются метрики**, **какие есть источники**, **какие API и вкладки UI**, **какой порядок обновлений**, **как запускать и проверять**.

---

**Содержание**
1. Общее назначение и архитектура
2. Компоненты системы
3. Данные и таблицы
4. Источники и ingestion (по шагам)
5. Атрибуция First/Last touch
6. Агрегации и кэш
7. Метрики и формулы
8. API (эндпоинты)
9. UI (вкладки и что в них показывается)
10. Планировщик, очереди и синхронизация
11. Конфигурация и переменные окружения
12. Запуск и окружение
13. Проверка корректности

---

## 1. Общее назначение и архитектура

**Цель**: единая аналитика по ботам (каждый бот = отдельная Postgres‑БД), рекламным компаниям и UTM‑меткам с полной воронкой (lead → platform → learning → interview → offer → contract), связкой с бюджетами и рекламными метриками, плюс Telegram‑подписки и атрибуция.

**Высокоуровневый поток данных**
- Источники (Postgres‑базы ботов, lead‑DB, PokerHub, Telegram Bot API, ручные бюджеты и рекламные метрики в Postgres)
- Ingestion → `raw_bot_users`
- Пересчёт атрибуции → поля `first_touch_*`, `last_touch_*`
- Агрегации → `agg_daily_new_users`, `agg_tg_subs_daily`
- Кэш отчётов → Redis
- API → UI

---

## 2. Компоненты системы

**Backend** (`backend/app`)
- FastAPI API‑сервис
- SQLAlchemy Async + Postgres
- RQ для фоновых задач
- Redis для кэша и блокировок

**Worker** (`backend/app/worker/tasks.py`)
- Очереди: основная `default` и отдельная `telegram`
- Планировщик (циклично проверяет интервалы и ставит задачи)

**Frontend** (`frontend/src`)
- React + MUI
- Вкладки аналитики и панели ввода бюджетов/метрик

**Хранилище**
- Postgres: основная БД аналитики, плюс внешние БД ботов и lead
- Redis: кэш отчётов, состояние синхронизаций, токены авторизации

---

## 3. Данные и таблицы

### 3.1 `raw_bot_users` — центральная таблица
Ключ: `(bot_key, tg_user_id)`.

Поля (ключевые):
- Идентификация: `bot_key`, `tg_user_id`, `username`, `created_at`, `ingested_at`
- UTM: `utm_source`, `utm_campaign`, `utm_medium`, `utm_content`, `utm_term`
- РК: `advertising_company`
- Бюджет на пользователя: `budget`
- Статусы воронки: `converted_to_lead`, `registered_platform`, `started_learning`, `completed_course`, `used_simulator`, `interview_reached`, `interview_passed`, `offer_received`, `contract_signed`
- Telegram: `channel_subscribed`, `community_member`
- Внутренние: `team_member`, `internal_status`, `user_block`
- PokerHub обучение: `learn_start_date`, `start_course`
- Атрибуция: `first_touch_bot`, `first_touch_campaign`, `last_touch_bot`, `last_touch_campaign`

### 3.2 Агрегаты
- `agg_daily_new_users` — дневная статистика пользователей и бюджета
- `agg_tg_subs_daily` — дневная статистика стартов и Telegram подписок по измерениям

### 3.3 Справочники
- `bot_registry` — человекочитаемые имена и активность ботов
- `advertising_companies` — справочник рекламных компаний
- `advertising_company_bots` — связь РК ↔ бот

### 3.4 Telegram и доступ
- `telegram_subscription_events` — история подписки/отписки
- `telegram_access` — whitelist на доступ в UI

### 3.5 Настройки и логи
- `system_settings` — настройки периодичности синхронизаций
- `sync_event_logs` — ошибки синхронизаций

### 3.6 Бюджеты и рекламные метрики
- `budget_weekly` — недельные бюджеты (ручной ввод)
- `ad_metrics_weekly` — недельные рекламные метрики (ручной ввод)

---

## 4. Источники и ingestion (по шагам)

### 4.1 Базы ботов (Postgres)
Файл: `backend/app/ingestion/ingestion_service.py`.

Как работает:
- **Бот = база**. `PostgresExplorer.list_bot_databases()` ищет БД, где есть таблица `users`.
- Для каждой БД определяется конфигурация (колонки и поля).
- Снимаются поля `tg_user_id`, `username`, `created_at`, UTM.
- Если есть таблица `lead_resources`, UTM берутся из неё.
- `created_at` ищется по кандидатам: `timestamp_registration`, `created_at`, `created`, `registered_at`, `reg_date`.
- Если в таблице есть `user_block` и БД не `lead`, поле пишется в `raw_bot_users.user_block`.
- Данные upsert по `(bot_key, tg_user_id)`.

Итого: наличие БД в Postgres = наличие бота. Название БД используется как `bot_key`.

См. `backend/app/ingestion/bot_remote_client.py` и `backend/app/ingestion/bot_config.py`.

### 4.2 Привязка ботов к рекламным компаниям
Файлы: `backend/app/services/advertising_company_service.py`.

Как работает:
- Через API админка задаёт список ботов для каждой РК.
- При ingestion ботов подставляется `advertising_company` из активной карты.
- Есть принудительный пересчёт `advertising_company` для всех пользователей.

### 4.3 Lead DB (converted_to_lead)
Файл: `backend/app/ingestion/lead_ingestor.py`.

Как работает:
- Из `lead` БД берутся `id` и `username`.
- `converted_to_lead = true` ставится по совпадению `tg_user_id` или username.

### 4.4 PokerHub (registered_platform, started_learning)
Два источника, два сценария:

1) **PokerHub cache из Postgres**
- Файл: `backend/app/ingestion/pokerhub_ingestor.py`
- Берёт таблицу `pokerhub_user_cache` в lead‑БД
- `registered_platform = true` для всех найденных
- `started_learning = true`, если в payload найдены курсы/уроки

2) **PokerHub cache из Redis**
- Файлы: `backend/app/services/pokerhub_cache_service.py` и `backend/app/ingestion/pokerhub_cache_ingestor.py`
- Сначала сервис получает данные по API и кладёт в Redis `ph:users:{tg_user_id}`
- Потом `PokerHubCacheIngestor` проходит по всем `tg_user_id` в `raw_bot_users` и обновляет:
  - `learn_start_date` (самая ранняя дата урока)
  - `start_course` (MTT / SPIN / CASH)
  - `started_learning = true`, если есть `learn_start_date` или `start_course`

### 4.5 Telegram подписки
Файл: `backend/app/ingestion/telegram_ingestor.py`.

Как работает:
- Для каждого пользователя проверяется `getChatMember` в канале и/или салоне.
- Изменения статуса пишутся в `telegram_subscription_events`.
- Текущие статусы записываются в `raw_bot_users.channel_subscribed` и `raw_bot_users.community_member`.
- Статусы также кэшируются в Redis.

---

## 4.6 Бюджеты и рекламные метрики (ручной ввод)

### 4.6.1 Бюджеты (`budget_weekly`)
API: `POST /api/budgets` (см. `backend/app/api/routers/budgets.py`).
Как работает:
- Бюджет задаётся **на неделю** (`week_start` приводится к понедельнику).
- Ключевые поля: `campaign` (имя РК), `bot_key` (опционально), `amount`, `currency`.
- При сохранении бюджета **автоматически обновляется** `ad_metrics_weekly.spend` для той же недели/кампании/бота.
Где используется:
- В отчёте `GET /api/reports/budgets/weekly` бюджет участвует в расчётах затрат и эффективности.

### 4.6.2 Рекламные метрики (`ad_metrics_weekly`)
API: `POST /api/ad-metrics` (см. `backend/app/api/routers/ad_metrics.py`).
Как работает:
- Метрики задаются **на неделю** (`week_start` приводится к понедельнику).
- Ключевые поля: `campaign`, `bot_key` (опционально), `impressions`, `clicks`, `spend`.
- Если `spend > 0`, то **в отчётах он заменяет бюджет** как источник фактических затрат.
Где используется:
- В `budget_weekly_report` (см. `backend/app/services/report_repository.py`) рассчитываются CTR, CPC, CPM, CPF, CPL, CPA, Cost Contract и т.д.

## 5. Атрибуция First/Last touch
Файл: `backend/app/services/attribution_service.py`.

### First Touch
- Берётся **самое раннее касание** по `created_at` среди всех записей пользователя.
- Исключаются боты из `FIRST_TOUCH_EXCLUDE_BOT_KEYS` и все `lead%`.
- Заполняются `first_touch_bot` и `first_touch_campaign`.

### Last Touch
- Берётся **последнее касание до `learn_start_date`**.
- Если `learn_start_date` отсутствует, `last_touch_*` остаются `нет метки`.
- Исключаются боты из `LAST_TOUCH_EXCLUDE_BOT_KEYS` и все `lead%`.

---

## 6. Агрегации и кэш

### 6.1 `agg_daily_new_users`
Файл: `backend/app/services/aggregate_refresher.py`.

Логика:
- Группировка по `day`, `bot_key`, `utm_source`, `utm_campaign`, `advertising_company`.
- Метрики: `users`, `budget`, `cac`.

### 6.2 `agg_tg_subs_daily`
Файл: `backend/app/services/aggregate_refresher.py`.

Логика:
- `bot_starts`: первый touch **не lead**
- `almanah_starts`: первый touch **lead%**
- Подписки/отписки берутся из `telegram_subscription_events`.
- Измерения: день + campaign + bot + advertising_company + UTM.

### 6.3 Кэш отчётов в Redis
Файл: `backend/app/services/report_cache_service.py`.

Кэшируются:
- `reports:total`
- `reports:daily`
- `reports:breakdown:utm_source`
- `reports:weekly:*`

Ключи обновляются после ingestion.

---

## 7. Метрики и формулы

### 7.1 Базовые метрики
- **Starts (entered)** = `COUNT(DISTINCT tg_user_id)` по `created_at`
- **Leads** = `converted_to_lead = true`
- **Platform** = `registered_platform = true`
- **Learning** = `started_learning = true`
- **Course** = `completed_course = true`
- **Interview / Offer / Contract** = соответствующие булевы поля

### 7.2 Бюджетные метрики (overview)
- **Budget** = `SUM(raw_bot_users.budget)`
- **CAC** = Budget / Starts

### 7.3 Отчёт по недельным бюджетам
Источник: `budget_weekly_report` в `backend/app/services/report_repository.py`.

Ключевые правила:
- Период по неделям или по дням (`interval=week|day`).
- Если `ad_metrics_weekly.spend > 0`, он заменяет `budget_weekly.amount` в расчётах.

Формулы:
- `spend_base = spend > 0 ? spend : budget`
- **CTR** = clicks / impressions
- **CPC (click)** = spend_base / clicks
- **CPM** = spend_base / impressions * 1000
- **CPF** = spend_base / subscribed
- **CPL** = spend_base / lead
- **CPA** = spend_base / learning
- **Cost Contract** = spend_base / contract

### 7.4 RAW Users (особое поле budget)
В RAW‑ответе поле `budget` — это **CPA по learning**, рассчитанный на уровне дня:
- берётся бюджет из `budget_weekly` и распределяется по дням
- делится на `learning` за день для данной РК/бота

Файл: `backend/app/services/raw_user_repository.py`.

---

## 8. API (эндпоинты)

### 8.1 Отчёты (`/api/reports`)
- `GET /funnel-start/total`
- `GET /funnel-start/daily`
- `GET /funnel-start/breakdown`
- `GET /funnel-start/conversions`
- `GET /funnel-start/stages`
- `GET /funnel-start/summary`
- `GET /funnel-start/raw`
- `GET /funnel-start/export`
- `GET /weekly`
- `GET /subscriptions/compare`
- `GET /courses/mix`
- `GET /touch/summary`
- `GET /touch/funnel-summary`
- `GET /touch/weekly`
- `GET /budgets/weekly`

Основные фильтры (общие):
- `start_date`, `end_date`
- `bots`, `advertising_companies`
- `utm_source`, `utm_campaign`, `utm_medium`, `utm_content`, `utm_term`

RAW‑фильтры:
- `raw_*` поля из `RawUserFilters` (`raw_tg_user_id`, `raw_converted_to_lead`, `raw_first_touch_present`, и т.д.).

### 8.2 Боты (`/api/bots`)
- `GET /api/bots` — список ботов и их активность
- `POST /api/bots/registry` — обновить имя/активность

### 8.3 Рекламные компании (`/api/advertising-companies`)
- `GET` — список РК
- `POST` — создать/обновить РК и назначить ботов
- `POST /rebuild` — пересчитать назначения

### 8.4 Бюджеты (`/api/budgets`)
- `GET` — список `budget_weekly`
- `POST` — создать
- `PUT /{id}` — обновить
- `DELETE /{id}` — удалить
- При создании/обновлении бюджета автоматически обновляется `ad_metrics_weekly.spend` на ту же неделю/кампанию/бота.

### 8.5 Рекламные метрики (`/api/ad-metrics`)
- `GET` — список `ad_metrics_weekly`
- `POST` — создать
- `PUT /{id}` — обновить
- `DELETE /{id}` — удалить

### 8.6 UTM (`/api/utm`)
- `GET /sources`, `/campaigns`, `/mediums`, `/contents`, `/terms`

### 8.7 Админка (`/api/admin`)
- `POST /ingest` — ingestion
- `POST /sync-telegram`
- `POST /sync-all`
- `POST /refresh-agg`
- `GET /sync-status`
- `GET /settings`, `PUT /settings`
- `GET /sync-logs`
- `GET /databases`, `GET /bot-databases`, `POST /query-db`
- `GET /telegram-access`, `POST /telegram-access`, `DELETE /telegram-access/{tg_user_id}`

### 8.8 Авторизация (`/api/auth` + `/api/telegram/webhook`)
- Telegram‑авторизация через bot + callback + JWT

---

## 9. UI (вкладки и что в них показывается)

### Overview
- Users, Total Budget, CAC
- Daily New Users график
- Breakdown по UTM/РК

### Funnel
- Полная воронка: entered → lead → platform → learning → ...

### TotalB
- Воронка по ботам
- Дополнительно: impressions, clicks, subscribed, spend, budget

### TotalA
- Воронка по рекламным компаниям
- Дополнительно: impressions, clicks, subscribed, spend, budget

### TotalC
- Воронка по First/Last touch
- Переключатель `first` / `last`

### TG SUBS
- Сравнение стартов и подписок/отписок
- День/неделя, группировка по РК

### RAW Users
- Таблица сырых пользователей
- Поддержка фильтров, сортировки, экспорта CSV

### RAW UTM
- Разбивка по UTM, выбор группировки

---

## 10. Планировщик, очереди и синхронизация

### Очереди
- `default` — ingestion и отчёты
- `telegram` — проверки Telegram

### Планировщик
Файл: `backend/app/worker/tasks.py`.

Логика:
- Раз в минуту проверяет, нужно ли ставить задачи
- Интервалы берутся из `system_settings` или env
- Использует Redis‑локи для защиты от дублей

Настройки:
- `INGESTION_SYNC_INTERVAL_MINUTES`
- `POKERHUB_SYNC_INTERVAL_HOURS`
- `TELEGRAM_SYNC_INTERVAL_MINUTES`
- `TELEGRAM_SYNC_DAILY_HOUR`

---

## 11. Конфигурация и переменные окружения

### Основные env
- `ANALYTICS_DB_DSN`
- `POSTGRES_ADMIN_DSN`
- `REDIS_URL`
- `RQ_QUEUE_NAME`
- `TELEGRAM_RQ_QUEUE_NAME`

### PokerHub
- `POKERHUB_API_URL`
- `POKERHUB_API_BATCH_SIZE`

### Telegram
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHANNEL_ID`
- `TELEGRAM_COMMUNITY_ID`
- `TELEGRAM_WEBHOOK_SECRET`

### Авторизация
- `AUTH_JWT_SECRET`
- `AUTH_ALLOW_UNKNOWN_USERS`
- `AUTH_START_TOKEN_TTL_SECONDS`
- `AUTH_SESSION_TTL_SECONDS`

### Прочее
- `LAST_TOUCH_EXCLUDE_BOT_KEYS`
- `FIRST_TOUCH_EXCLUDE_BOT_KEYS`
- `CACHE_TTL_SECONDS`

---

## 12. Запуск и окружение

### Backend + Frontend
```bash
scripts/run_app.sh
```

### Worker
```bash
scripts/run_worker.sh
```

### Telegram‑worker
```bash
scripts/run_worker_telegram.sh
```


