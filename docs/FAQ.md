# Полный FAQ: Analytic System

> Последнее обновление: 2026-04-26  
> Стек: PostgreSQL · FastAPI · Redis · RQ · React 18 · TypeScript

---

## Оглавление

1. [Архитектура системы](#1-архитектура-системы)
2. [База данных — все таблицы и поля](#2-база-данных--все-таблицы-и-поля)
3. [Воронка — точные определения каждого шага](#3-воронка--точные-определения-каждого-шага)
4. [Attribution: first_touch и last_touch](#4-attribution-first_touch-и-last_touch)
5. [Timezone — почему всё в MSK](#5-timezone--почему-всё-в-msk)
6. [Источники данных и Ingestion](#6-источники-данных-и-ingestion)
7. [Агрегаты и пересчёт](#7-агрегаты-и-пересчёт)
8. [Кэш Redis — стратегия и TTL](#8-кэш-redis--стратегия-и-ttl)
9. [Все метрики и формулы](#9-все-метрики-и-формулы)
10. [Вкладки дашборда — откуда данные, как считается](#10-вкладки-дашборда--откуда-данные-как-считается)
11. [API Endpoints — полная карта](#11-api-endpoints--полная-карта)
12. [Авторизация](#12-авторизация)
13. [Фильтры и их семантика](#13-фильтры-и-их-семантика)
14. [Worker и очередь RQ](#14-worker-и-очередь-rq)
15. [Часто задаваемые вопросы](#15-часто-задаваемые-вопросы)

---

## 1. Архитектура системы

### Стек

| Слой | Технология |
|------|-----------|
| БД | PostgreSQL 15 (asyncpg driver) |
| Кэш / очередь | Redis 7 |
| Фоновые задачи | RQ (Redis Queue) |
| API | FastAPI 0.111 + SQLAlchemy 2 (async) |
| Репликация | WAL logical replication (PostgreSQL → PostgreSQL) |
| Frontend | React 18 + TypeScript + MUI 5 + Vite |
| Auth | JWT-cookie + Telegram OTP |

### Вкладки дашборда (актуальные)

| Ключ | Название в сайдбаре |
|------|---------------------|
| `overview` | Overview |
| `totalb` | BOTs |
| `main` | Основной отчёт |
| `tgsubs` | TG SUBS |
| `lessons` | PokerHub |
| `raw` | RAW Users |
| `usersearch` | Поиск |
| `faq` | FAQ |

### Схема потока данных

```
Telegram-боты          Google Sheets (SM-данные)   PokerHub API
     │                        │                          │
     ▼                        ▼                          ▼
raw_bot_users          google_sheets_ingestor     pokerhub_ingestor
  (ингестия)             (статусы воронки)          (platform-данные)
     │                        │                          │
     └──────────────────────┬─┘                          │
                             ▼                           │
                   AttributionService              replication_worker
                 (first/last touch update)           (ph_user_mirror_replica)
                             │                           │
                             ▼                           │
                  aggregate_refresher ◄──────────────────┘
                 (agg_daily / agg_tg_subs /
                  agg_weekly_funnel_bot/company)
                             │
                             ▼
                   Redis Cache (TTL 5min–24h)
                             │
                             ▼
                     FastAPI REST API
                             │
                             ▼
                    React Dashboard
```

### Процессы

- **uvicorn** — основной HTTP-сервер (FastAPI)
- **rq worker** (очередь `default`) — тяжёлые задачи: ингестия, attribution, poke-hub sync
- **rq worker** (очередь `telegram`) — Telegram-синхронизация, membership-сканер
- **periodic_sync** — внутренний планировщик FastAPI (asyncio tasks), запускает синки по расписанию

---

## 2. База данных — все таблицы и поля

### `raw_bot_users` — главная рабочая таблица

Один ряд = одна пара **(bot_key, tg_user_id)**. Если пользователь взаимодействовал с 3 ботами — 3 строки с одинаковым `tg_user_id`.

| Поле | Тип | Смысл |
|------|-----|-------|
| `id` | int PK | Внутренний ID |
| `bot_key` | str(64) | Идентификатор бота, напр. `almanah_ru` |
| `tg_user_id` | bigint | Telegram User ID |
| `username` | str(128) | @username в Telegram |
| `user_block` | bool | Пользователь заблокировал бота |
| `created_at` | timestamptz | Когда впервые появился в этом боте |
| `ingested_at` | timestamptz | Когда мы это обработали |
| `utm_source` | str | UTM бота (откуда пришёл в бот) |
| `utm_campaign` | str | UTM-кампания бота |
| `utm_medium` | str | UTM-medium бота |
| `utm_content` | str | UTM-content бота |
| `utm_term` | str | UTM-term бота |
| `platform_utm_source` | str | UTM платформы (откуда зарегистрировался на PokerHub) |
| `platform_utm_campaign` | str | UTM-кампания платформы |
| `platform_utm_medium` | str | UTM-medium платформы |
| `platform_utm_content` | str | UTM-content платформы |
| `platform_utm_term` | str | UTM-term платформы |
| `advertising_company` | str(128) | Привязанная рекламная компания |
| `converted_to_lead` | bool | Перешёл в лид-бот |
| `registered_platform` | bool | Зарегистрировался на PokerHub |
| `platform_registered_at` | timestamptz | Дата регистрации на платформе |
| `started_learning` | bool | Начал обучение (есть `learn_start_date`) |
| `completed_course` | bool | Прошёл курс |
| `completed_course_at` | timestamptz | Дата завершения курса |
| `used_simulator` | bool | Использовал симулятор |
| `interview_reached` | bool | Дошёл до собеседования |
| `interview_passed` | bool | Прошёл собеседование |
| `offer_received` | bool | Получил оффер |
| `contract_signed` | bool | Подписал контракт |
| `interview_reached_status` | text | Текстовый статус (напр. "отказали", "наигрывают дистанцию") |
| `offer_received_status` | text | Текстовый статус оффера |
| `distance_grinding` | bool | Наигрывает дистанцию (особый статус) |
| `channel_subscribed` | bool | Подписан на основной Telegram-канал |
| `channel_subscribed_at` | timestamptz | Дата подписки |
| `community_member` | bool | Участник сообщества |
| `learn_start_date` | timestamptz | Дата старта обучения |
| `start_course` | str(32) | Курс (`MTT`, `SPIN`, `CASH`) |
| `ph_user_id` | int | ID пользователя на PokerHub |
| `first_touch_bot` | str(128) | Бот первого касания (заполняется AttributionService) |
| `first_touch_campaign` | str(128) | UTM-кампания первого касания |
| `last_touch_bot` | str(128) | Бот последнего касания до регистрации на платформе |
| `last_touch_campaign` | str(128) | UTM-кампания последнего касания |

**UniqueConstraint**: `(bot_key, tg_user_id)` — пара уникальна.

### `ph_user_mirror_replica` — зеркало PokerHub

Реплицируется WAL-репликатором. Хранит актуальный снимок пользователя с платформы.

Ключевые поля:
- `ph_id` — ID на платформе
- `lessons` — JSON-массив пройденных уроков, напр. `["MTT1: Базовый курс", "SPIN1: ГТО"]`
- `courses`, `groups`, `course_memberships` — JSON
- `source_updated_at` — время обновления в источнике
- `synced_at` — время нашей репликации

### Агрегатные таблицы

| Таблица | Группировка | Счётчики |
|---------|-------------|---------|
| `agg_daily_new_users` | день + bot_key + utm + company | users, budget, cac |
| `agg_tg_subs_daily` | день + campaign + bot_key + company + utm | bot_starts, almanah_starts, channel_subscribed/unsubscribed, saloon_subscribed/unsubscribed |
| `agg_weekly_funnel_bot` | неделя + bot_key | entered, new_in_system, old_in_system, lead, subscribed, platform, learning, course, simulator, interview, passed, offer, contract, distance_grinding |
| `agg_weekly_funnel_company` | неделя + advertising_company | те же этапы |

### Прочие таблицы

| Таблица | Назначение |
|---------|-----------|
| `budget_weekly` | Бюджеты по неделям и кампаниям (вводятся вручную) |
| `ad_metrics_weekly` | Рекламные метрики: impressions, clicks, spend |
| `bot_registry` | Реестр ботов: bot_key, display_name, canonical_base |
| `advertising_companies` | Рекламные компании с UTM-правилами |
| `telegram_subscription_events` | События подписки/отписки (bot_poll) |
| `telegram_chat_memberships` | Актуальное членство (MTProto-сканер) |
| `telegram_chat_totals` | Общий счётчик участников канала |
| `employee_registry` | Сотрудники — исключаются из всей аналитики |
| `system_settings` | Произвольные настройки (key → JSON) |
| `sync_event_logs` | Лог синхронизаций |
| `replication_dlq` | Dead Letter Queue репликации |

---

## 3. Воронка — точные определения каждого шага

Воронка **строго последовательная** — каждый следующий шаг включает всех из предыдущего.

| Шаг | Название | Условие |
|-----|----------|---------|
| 1 | **Entered** | `COUNT(DISTINCT tg_user_id)` — все уники за период |
| 2 | **New in system** | Первое появление в системе (дата этой записи = дата первого появления вообще) |
| 3 | **Old in system** | Уже был в другом боте раньше (`MIN(created_at) по всем ботам < created_at этой записи`) |
| 4 | **Lead** | `converted_to_lead IS TRUE` или `bot_key LIKE 'lead%'` |
| 5 | **Subscribed** | `channel_subscribed IS TRUE` |
| 6 | **Platform** | `registered_platform IS TRUE` + `ph_user_id IS NOT NULL` + `platform_registered_at IS NOT NULL` |
| 7 | **Learning** | Зарегистрировался на курс в PH (по `ph_user_mirror_replica.lessons`) |
| 8 | **Started Learning** | `started_learning IS TRUE` или `learn_start_date IS NOT NULL` |
| 9 | **Course** | `completed_course IS TRUE` + `completed_course_at IS NOT NULL` + `completed_course_at >= created_at` |
| 10 | **Interview** | `interview_reached IS TRUE` |
| 11 | **Passed** | `interview_passed IS TRUE` |
| 12 | **Offer** | `offer_received IS TRUE` |
| 13 | **Contract** | `contract_signed IS TRUE` |
| 14 | **Distance Grinding** | `distance_grinding IS TRUE` |

**Откуда берутся статусы:**
- `converted_to_lead`, `channel_subscribed`, `started_learning` — из ингестии Telegram-ботов
- `registered_platform`, `platform_registered_at` — из PokerHub API
- `completed_course`, `interview_reached`, `offer_received`, `contract_signed` — из Google Sheets (SM-таблица)
- `distance_grinding` — парсится из текстовых статусов Google Sheets: "наигрывают_дистанцию"

### New vs Old in system

```sql
first_seen_at_system = MIN(created_at) по всем ботам для данного tg_user_id

new_in_system: first_seen_at_system = created_at   -- впервые появился именно сейчас
old_in_system: first_seen_at_system < created_at   -- уже видели в другом боте раньше
```

Важно: эти шаги **не суммируются** в Entered. `new + old = entered` всегда.

---

## 4. Attribution: first_touch и last_touch

`AttributionService.rebuild()` обновляет поля `first_touch_bot` / `last_touch_bot` / `_campaign` одним `UPDATE ... WITH CTE`.

### first_touch

Самый ранний бот пользователя, исключая lead-боты.

```sql
SELECT DISTINCT ON (tg_user_id)
    tg_user_id, bot_key,
    COALESCE(platform_utm_campaign, utm_campaign, 'нет метки')
FROM raw_bot_users
WHERE lower(trim(bot_key)) NOT LIKE 'lead%'
  AND lower(trim(bot_key)) != ALL(:excluded_bots)
ORDER BY tg_user_id, created_at ASC    -- САМЫЙ РАННИЙ
```

### last_touch

Последний бот пользователя **до даты регистрации на платформе** (`platform_registered_at`).  
Пользователи без `platform_registered_at` — `last_touch = 'нет метки'`.

```sql
-- Только пользователи с регистрацией на платформе:
JOIN platform_users ON platform_users.tg_user_id = raw.tg_user_id
WHERE raw.created_at <= platform_users.platform_registered_at  -- граница
ORDER BY raw.tg_user_id, raw.created_at DESC   -- САМЫЙ ПОЗДНИЙ до регистрации
```

**Почему граница — `platform_registered_at`, а не `learn_start_date`?**  
Регистрация на платформе — точка конверсии. Пользователь мог начать учиться через несколько недель после регистрации, при этом сменив боты. Правильная граница — момент, когда он стал клиентом.

### event-mode

Режим по умолчанию. Attribution не используется — группировка по `advertising_company` записи в `raw_bot_users`. Самый быстрый и простой режим.

---

## 5. Timezone — почему всё в MSK

Все даты хранятся как `timestamptz` (UTC). При расчётах переводятся в московское время:

```sql
date_trunc('week', created_at AT TIME ZONE 'Europe/Moscow')::date
```

В SQLAlchemy используется `text("'Europe/Moscow'")` вместо строки — иначе SQLAlchemy создаёт два отдельных `$N`-параметра для SELECT и GROUP BY, и PostgreSQL видит их как разные выражения → ошибка `column must appear in GROUP BY`.

---

## 6. Источники данных и Ingestion

| Источник | Файл | Интервал | Что обновляет |
|----------|------|----------|---------------|
| Telegram-боты | `pokerhub_ingestor.py` | По событию | `raw_bot_users`: базовые поля, флаги воронки |
| PokerHub API | `pokerhub_ingestor.py` | 5 мин | `ph_user_id`, `platform_registered_at`, `learn_start_date`, `start_course` |
| Google Sheets (SM) | `google_sheets_ingestor.py` | 5 мин | `completed_course`, `interview_reached`, `offer_received`, `contract_signed`, `distance_grinding` |
| WAL Replication | `replication_worker.py` | Непрерывно | `ph_user_mirror_replica` — зеркало PokerHub |
| Telegram MTProto | `telegram_membership_service.py` | Ежедневно 4:00 МСК | `telegram_chat_memberships`, `telegram_chat_totals` |
| Attribution | `attribution_service.py` | После ингестии | `first_touch_bot`, `last_touch_bot` |

**Логика Google Sheets-инжестора**: сначала **сбрасывает** interview/offer/contract/distance флаги до FALSE для всех лид-пользователей, потом проставляет заново из таблицы. Это гарантирует, что удалённые строки из Sheets не остаются "зомби"-статусами.

---

## 7. Агрегаты и пересчёт

**Глубина**: 90 дней (`aggregate_refresh_days` из `.env`).

**Когда пересчитывается:**
1. Автоматически — `replication_worker` после каждого батча (с дебаунсом ~60с)
2. Вручную — admin-панель → "Refresh Aggregates" или `POST /api/admin/refresh-agg`

**Почему 90 дней, а не полная история?** Производительность. Данные старше 90 дней не изменяются. Первый полный пересчёт делался вручную при запуске системы.

**После деплоя**: если изменились формулы агрегации — нужно вручную запустить пересчёт через admin-панель.

---

## 8. Кэш Redis — стратегия и TTL

| Тип запроса | TTL | Примечание |
|-------------|-----|-----------|
| Стандартные отчёты | **5 мин** | `cache_ttl_seconds` |
| Недельные агрегаты (companies-weekly) | **24 ч** | `weekly_cache_ttl_seconds` |
| Stale-кэш недельных данных | **7 сут** | Резерв при недоступности БД |
| Фильтрованные запросы (bots/companies) | **не кэшируются** | Слишком много комбинаций |

**Stale-кэш**: когда основной кэш протух или БД недоступна, отдаётся stale-версия. Дашборд работает даже при обслуживании БД.

**Frontend-кэш**: `localStorage`, ключ `v15_*`, TTL 12 часов. При открытии страницы сразу показывается кэш, параллельно загружаются свежие данные.

---

## 9. Все метрики и формулы

### Бюджетные метрики (вкладка Основной отчёт)

```
spend_base = spend  если spend > 0
           = budget если spend = 0  (используем плановый бюджет)

CPF     = spend_base / subscribed      Cost per Follow — стоимость подписчика в канал
CPL     = spend_base / lead            Cost per Lead — стоимость лида (переход в лид-бот)
CPA     = spend_base / learning        Cost per Acquisition = стоимость старта обучения
CPC     = spend_base / contract        Cost per Contract (НЕ клик!)
CTR     = clicks / impressions × 100  Click-Through Rate, %
CPCₗ    = spend_base / clicks          Cost per Click по рекламному объявлению
CPM     = spend_base / impressions × 1000   Cost per Mille (1000 показов)
```

Если знаменатель = 0 → метрика = `null` (не показывается, а не 0/∞).  
Все суммы в **USD** (мультивалютности нет).

### Конверсии воронки

```
CR(A → B) = count(B) / count(A) × 100%
```

### Course Mix

```
MTT%  = mtt  / total_learning × 100
SPIN% = spin / total_learning × 100
CASH% = cash / total_learning × 100
```

---

## 10. Вкладки дашборда — откуда данные, как считается

### Overview

**Endpoint**: `/api/reports/funnel-start/stages`  
KPI-карточки за выбранный период: Entered, Lead, Platform, Learning, Course, Interview, Offer, Contract.  
График "Daily New Users" из `agg_daily_new_users`.  
Источник агрегатов — `agg_weekly_funnel_bot` + прямые запросы к `raw_bot_users`.

### BOTs (вкладка `totalb`)

**Endpoint**: `GET /api/reports/roistat-weekly/companies-weekly`  
Использует `bot_rows` из ответа (разбивка по bot_key × неделя).  
Каждая строка = один бот, агрегат по всему выбранному периоду.  
При раскрытии строки → `GroupWeeklyStats` вызывает тот же endpoint с фильтром `bots=<bot_key>` → помесячная разбивка.

**Этапы в BOTs**: entered_all → almanah_starts → platform_cnt → started_learning → completed_course → interview_reached → offer_received → contract_signed

**almanah_starts** — пользователи, которые пришли через almanah-бот (не direct_source).  
**direct_source_cnt** — прямой источник: `bot_key LIKE 'lead%'` + `ph_user_id = tg_user_id`.

### Основной отчёт (вкладка `main`)

**Endpoint**: `GET /api/reports/roistat-weekly/companies-weekly` с `display_mode=weekly`  
Самый детальный отчёт: неделя × РК × бот.  
Содержит: метрики воронки + бюджет + рекламные метрики (impressions, clicks, spend, CTR, CPM, CPC).  
Компонент: `MainReportTable.tsx`, хук: `useMainReport.ts` (localStorage-кэш v15, TTL 12h).

### TG SUBS (вкладка `tgsubs`)

**Endpoint**: `GET /api/reports/subscriptions/compare`  
Источник: `agg_tg_subs_daily` (агрегат по дням).  
Показывает: подписки/отписки по дням, сравнение основной канал vs сообщество.  
"Не в боте" = участники канала, которых нет в `raw_bot_users`.  
Данные MTProto из `telegram_chat_memberships` (полный снимок).

### PokerHub (вкладка `lessons`)

**Endpoint**: `GET /api/reports/roistat-lessons`  
Матрица уроков по пользователям из `ph_user_mirror_replica.lessons`.  
Работает по lead-когорте (внутренний фильтр `bots=[lead]`).  
Показывает прогресс по урокам, курсам, датам — для анализа учебного пути.

### RAW Users (вкладка `raw`)

**Endpoint**: `GET /api/reports/funnel-start/raw`  
Постраничная таблица `raw_bot_users` — сырые строки без агрегирования.  
**1 строка ≠ 1 пользователь** — у одного человека может быть несколько строк (по числу ботов).  
Используется для диагностики, проверки first/last touch, поиска расхождений.  
Сотрудники (`employee_registry`) исключены.

### Поиск (вкладка `usersearch`)

Поиск по `tg_user_id` или `username`.  
Показывает всю историю пользователя: все боты, все даты, all этапы, first/last touch.  
Верхние фильтры не применяются.

---

## 11. API Endpoints — полная карта

### Reports

```
GET  /api/reports/funnel-start/total          — общий счёт пользователей + бюджет
GET  /api/reports/funnel-start/daily          — дневная динамика
GET  /api/reports/funnel-start/breakdown      — разбивка по бот/РК
GET  /api/reports/funnel-start/stages         — агрегат по этапам воронки
GET  /api/reports/funnel-start/summary        — сводка по боту или РК
GET  /api/reports/funnel-start/summary-weekly — недельная сводка одной группы
GET  /api/reports/funnel-start/tree           — дерево: платформа → кабинет → бот
GET  /api/reports/funnel-start/raw            — сырые строки raw_bot_users
GET  /api/reports/funnel-start/export         — экспорт RAW в CSV/XLSX

GET  /api/reports/roistat-weekly/companies-weekly  — ГЛАВНЫЙ endpoint (BOTs / Основной отчёт)
     Параметры:
       event_start, event_end       — период событий (created_at)
       first_touch_start/end        — период first touch
       mode                         — event / first_touch / last_touch
       display_mode                 — weekly / cohort (по умолчанию weekly)
       bots[]                       — фильтр по bot_key
       advertising_companies[]      — фильтр по компании
       utm_source/campaign/medium/content/term
     Ответ: { rows[], bot_rows[], week_totals[] }

GET  /api/reports/roistat-weekly               — Weekly из Google Sheets
GET  /api/reports/roistat-lessons              — матрица уроков PokerHub
GET  /api/reports/subscriptions/compare        — TG подписки vs старты
GET  /api/reports/courses/mix                  — разрез курсов MTT/SPIN/CASH
GET  /api/reports/touch/summary                — атрибуция first/last touch
GET  /api/reports/touch/funnel-summary         — воронка по touch
GET  /api/reports/budgets/weekly               — бюджет + воронка + рекламные метрики
```

### Admin

```
POST /api/admin/ingest                     — запустить ингестию
POST /api/admin/sync-pokerhub              — синк PokerHub API
POST /api/admin/sync-google-sheets         — синк Google Sheets
POST /api/admin/refresh-agg               — пересчитать агрегаты
POST /api/admin/sync-all                  — все синки
POST /api/admin/sync-advertising-budget   — синк бюджетов
GET  /api/admin/status                    — статус системы
GET  /api/admin/sync-status               — статус последних синков
GET  /api/admin/data-sources-status       — статус источников данных
GET  /api/admin/sync-logs                 — лог синхронизаций
GET/POST/DELETE /api/admin/telegram-access      — управление доступом
GET/POST/DELETE /api/admin/employee-registry    — управление сотрудниками
GET  /api/admin/replication/metrics       — метрики WAL-репликации
GET  /api/admin/replication/dlq           — dead letter queue
GET  /api/admin/utm-coverage              — покрытие UTM-меток
```

---

## 12. Авторизация

**Механизм**: Telegram OTP + JWT HttpOnly cookie.

**Поток:**
1. Пользователь вводит Telegram ID
2. `POST /api/auth/telegram/start` → бот отправляет одноразовый код в личку
3. `POST /api/auth/telegram/confirm` → код проверяется, выдаётся JWT в cookie
4. Все запросы аутентифицированы через cookie автоматически

**Кто имеет доступ:**
- `initial_allowed_telegram_ids` из `.env` (всегда, без записи в БД)
- Все `tg_user_id` из таблицы `telegram_access`

TTL токена: 7 дней. Cookie: `HttpOnly`, `Secure`, `SameSite=lax`.

**Добавить пользователя:** admin-панель → Доступы → добавить `tg_user_id`.

---

## 13. Фильтры и их семантика

### Временные фильтры

| Параметр | Смысл |
|----------|-------|
| `event_start / event_end` | `created_at` в `raw_bot_users` — когда пришёл в бот |
| `first_touch_start / first_touch_end` | Дата первого касания (для first/last touch режимов) |

### Режимы attribution (touchMode)

| Режим | Смысл |
|-------|-------|
| `event` | Группировка по `advertising_company` записи (по умолчанию) |
| `first_touch` | Группировка по боту первого касания |
| `last_touch` | Группировка по боту последнего касания до регистрации |

### UTM-фильтры

Два набора UTM: **bot UTM** (`utm_*`) и **platform UTM** (`platform_utm_*`).  
Логика фильтра: **OR** — `(utm_source = X) OR (platform_utm_source = X)`.  
Нормализация: нижний регистр + trim. `None` / `'(none)'` → `'нет метки'`.

### Фильтр по ботам в first/last touch режимах

В режиме `event` фильтр `bots=[]` передаётся в SQL напрямую.  
В режимах `first_touch` / `last_touch` — серверный фильтр обнуляет данные для non-lead-ботов. Поэтому фронтенд получает все данные и фильтрует на клиенте.

### Исключение сотрудников

Во всех отчётах: `AND tg_user_id NOT IN (SELECT tg_user_id FROM employee_registry)`.

---

## 14. Worker и очередь RQ

| Очередь | Задачи |
|---------|--------|
| `default` | Ингестия, attribution, PokerHub sync, агрегаты |
| `telegram` | Telegram-подписки, MTProto-сканер |

**Важно после деплоя**: workers не перезапускаются автоматически. Если обновили код — нужно вручную перезапустить worker, иначе он работает со старым кодом в памяти.

**Дебаунс агрегации**: после batch-обработки ставится delayed_refresh с задержкой ~60с. Последующие запросы на агрегацию в эти 60с игнорируются.

---

## 15. Часто задаваемые вопросы

**Q: Почему "Недельных данных пока нет" при раскрытии бота в BOTs?**  
Исправлено 2026-04-26. Причина: BOTs не передавал `weeklySource="main_report"` в `GroupWeeklyStats`, поэтому использовался старый endpoint `reports/weekly` с пустыми данными.

**Q: Почему числа в BOTs не равны сумме по неделям в Основном отчёте?**  
BOTs агрегирует за весь период (пользователь считается 1 раз). Основной отчёт — каждая неделя отдельно. Один пользователь в двух неделях = 2 строки в Основном отчёте, 1 строка в BOTs.

**Q: Почему first_touch_bot / last_touch_bot = "нет метки"?**  
first_touch: пользователь входил только через lead-боты (исключены из расчёта).  
last_touch: у пользователя нет `platform_registered_at` (не зарегистрировался на платформе).

**Q: Почему агрегаты только за 90 дней?**  
Производительность. Данные старше 90 дней не меняются. Первый полный пересчёт делался вручную при запуске.

**Q: Что такое "distance_grinding"?**  
Особый HR-статус: пользователь прошёл курс, ему поставлена задача наиграть определённое количество рук перед следующим шагом. Парсится из текстовых статусов Google Sheets.

**Q: Почему кампания = "нет метки" если UTM есть?**  
Нормализация: `None`, `''`, `'(none)'`, `'-'`, `'none'`, `'null'`, `'нет метки'` → `'нет метки'`. Неатрибутированный трафик честно помечается.

**Q: Что такое almanah_starts vs lead vs entered?**  
`entered` = все пользователи в боте за период.  
`almanah_starts` = только те, кто пришёл через almanah-боты (органический источник).  
`direct_source` = прямые платные лиды (lead_bot + ph_user_id = tg_user_id).

**Q: Зачем нужны telegram_chat_memberships если есть telegram_subscription_events?**  
`telegram_subscription_events` — события от ботов (могут быть неполными).  
`telegram_chat_memberships` — полный снимок через MTProto (точный состав канала).  
Комбинация обоих даёт более точную картину.

**Q: Что делать если агрегаты "сломались" после деплоя?**  
Admin-панель → Refresh Aggregates, дождаться ~30-60 сек. При необходимости — Attribution Rebuild.
