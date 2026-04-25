<div align="center">

# 📊 Analytic System

**Сквозная маркетинговая аналитика для Telegram-ботов → PokerHub**

[![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/React-18-61DAFB?logo=react&logoColor=black)](https://react.dev)
[![TypeScript](https://img.shields.io/badge/TypeScript-5-3178C6?logo=typescript&logoColor=white)](https://typescriptlang.org)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15-4169E1?logo=postgresql&logoColor=white)](https://postgresql.org)
[![Redis](https://img.shields.io/badge/Redis-7-DC382D?logo=redis&logoColor=white)](https://redis.io)

</div>

---

## Что это

Внутренняя платформа сквозной аналитики: отслеживает путь пользователя от первого касания в Telegram-боте до подписания контракта. Объединяет данные из Telegram-ботов, PokerHub API, Google Sheets и рекламных кабинетов в единый дашборд.

**Воронка:** Entered → Lead → Platform → Learning → Course → Interview → Offer → Contract

---

## Стек

| Слой | Технология |
|------|-----------|
| API | FastAPI + SQLAlchemy 2 (async) |
| БД | PostgreSQL 15 (asyncpg) |
| Кэш / Очередь | Redis 7 + RQ |
| Репликация | WAL logical replication |
| Frontend | React 18 + TypeScript + MUI 5 + Vite |
| Auth | JWT HttpOnly cookie + Telegram OTP |

---

## Вкладки дашборда

| Вкладка | Что показывает |
|---------|---------------|
| **Overview** | KPI-карточки, график новых пользователей, сводка по воронке |
| **BOTs** | Воронка по каждому Telegram-боту с помесячной разбивкой |
| **Основной отчёт** | Недели × РК × Боты: воронка + бюджет + CPF/CPL/CPA/CPC/CTR/CPM |
| **TG SUBS** | Подписки/отписки Telegram-каналов, сравнение bot_poll vs MTProto |
| **PokerHub** | Матрица уроков пользователей по курсам MTT/SPIN/CASH |
| **RAW Users** | Сырая таблица raw_bot_users с поиском, фильтрами и экспортом |
| **Поиск** | История конкретного пользователя: все боты, этапы, first/last touch |
| **FAQ** | Встроенная документация с формулами и логикой расчётов |

---

## Архитектура

```
Telegram-боты          Google Sheets (SM)     PokerHub API
      │                       │                     │
      ▼                       ▼                     ▼
 raw_bot_users     google_sheets_ingestor   pokerhub_ingestor
      │                       │                     │
      └─────────────┬─────────┘                     │
                    ▼                               │
          AttributionService                replication_worker
        (first / last touch)              (ph_user_mirror_replica)
                    │                               │
                    ▼                               │
         aggregate_refresher  ◄────────────────────┘
       (agg_daily / agg_tg_subs /
        agg_weekly_funnel_bot/company)
                    │
                    ▼
          Redis Cache (5min – 24h)
                    │
                    ▼
            FastAPI REST API
                    │
                    ▼
           React Dashboard
```

---

## Быстрый старт

### 1. Переменные окружения

Скопируйте `.env.example` → `.env` и заполните:

```bash
# База данных
ANALYTICS_DB_DSN=postgresql+asyncpg://user:pass@localhost:5432/analytics
POSTGRES_ADMIN_DSN=postgresql+asyncpg://user:pass@localhost:5432/postgres

# Redis
REDIS_URL=redis://localhost:6379/0

# Telegram Bot (для авторизации)
TELEGRAM_BOT_TOKEN=...
TELEGRAM_BOT_USERNAME=...
TELEGRAM_CHANNEL_ID=...
TELEGRAM_COMMUNITY_ID=...

# Google Sheets (статусы SM)
GOOGLE_SHEETS_CREDENTIALS_PATH=/path/to/creds.json
GOOGLE_SHEETS_SM_SPREADSHEET_ID=...

# Auth
AUTH_JWT_SECRET=your-secret-key
```

### 2. Backend

```bash
cd backend
pip install -r requirements.txt

# Миграции
alembic upgrade head

# Запуск API
uvicorn app.main:app --host 0.0.0.0 --port 8000

# RQ Workers (в отдельных терминалах)
rq worker -u $REDIS_URL default
rq worker -u $REDIS_URL telegram
```

### 3. Frontend

```bash
cd frontend
npm install
npm run dev        # dev-сервер на :5173
npm run build      # production-сборка
```

### 4. Первый запуск данных

```bash
# Через admin-панель дашборда:
# 1. Admin → Sync All (запускает все источники)
# 2. Admin → Refresh Aggregates (пересчёт агрегатов)
# 3. Admin → Attribution Rebuild (first/last touch)
```

---

## Структура проекта

```
analytic-system/
├── backend/
│   ├── app/
│   │   ├── api/routers/          # FastAPI endpoints
│   │   │   ├── reports*.py       # Отчёты и воронка
│   │   │   ├── admin*.py         # Admin API
│   │   │   └── auth.py           # Авторизация
│   │   ├── core/
│   │   │   ├── config.py         # Настройки (pydantic-settings)
│   │   │   ├── redis_client.py   # Redis-клиент
│   │   │   └── periodic_sync.py  # Планировщик синков
│   │   ├── ingestion/
│   │   │   ├── pokerhub_ingestor.py        # Telegram-боты + PokerHub API
│   │   │   ├── google_sheets_ingestor.py   # SM Google Sheets
│   │   │   ├── replication_worker.py       # WAL replication
│   │   │   └── telegram_ingestor.py        # Telegram-события
│   │   ├── models/
│   │   │   └── analytics.py      # Все SQLAlchemy-модели
│   │   ├── services/
│   │   │   ├── attribution_service.py      # first/last touch
│   │   │   ├── aggregate_refresher*.py     # Агрегаты
│   │   │   ├── report_repository*.py       # SQL отчётов
│   │   │   └── telegram_membership_service.py  # MTProto
│   │   └── worker/
│   │       └── tasks.py          # RQ-задачи
│   └── tests/                    # 69 тестов
├── frontend/
│   └── src/
│       ├── components/           # UI-компоненты
│       │   ├── FunnelSummaryTable.tsx  # BOTs / воронка
│       │   ├── MainReportTable.tsx     # Основной отчёт
│       │   ├── FaqPanel.tsx            # FAQ
│       │   └── layout/OverviewPage.tsx # Главная страница
│       └── hooks/                # Data-хуки (useMainReport и др.)
├── docs/
│   ├── FAQ.md                    # Полный технический FAQ
│   └── wiki/                     # Wiki по вкладкам
└── infra/                        # Docker, nginx, деплой
```

---

## Ключевые API-эндпоинты

```
GET  /api/reports/roistat-weekly/companies-weekly   # BOTs + Основной отчёт
GET  /api/reports/funnel-start/stages               # Overview KPI
GET  /api/reports/subscriptions/compare             # TG SUBS
GET  /api/reports/roistat-lessons                   # PokerHub уроки
GET  /api/reports/funnel-start/raw                  # RAW Users

POST /api/admin/refresh-agg                         # Пересчёт агрегатов
POST /api/admin/sync-all                            # Все синки
POST /api/advertising/rebuild-attribution           # Attribution rebuild

POST /api/auth/telegram/start                       # Telegram OTP
POST /api/auth/telegram/confirm                     # Подтверждение + JWT
```

Полная карта эндпоинтов — [docs/FAQ.md → API Endpoints](docs/FAQ.md#11-api-endpoints--полная-карта)

---

## Attribution

Система определяет источник каждого пользователя двумя способами:

- **first_touch** — самый ранний Telegram-бот пользователя (исключая lead-боты)
- **last_touch** — последний бот до регистрации на платформе (`platform_registered_at`)

Обновляется одним `UPDATE ... WITH CTE` после каждой ингестии.

---

## Формулы метрик

| Метрика | Формула | Расшифровка |
|---------|---------|-------------|
| CPF | `spend / subscribed` | Стоимость подписчика в канал |
| CPL | `spend / lead` | Стоимость лида |
| CPA | `spend / learning` | Стоимость старта обучения |
| CPC | `spend / contract` | Стоимость контракта |
| CTR | `clicks / impressions × 100` | Кликабельность, % |
| CPM | `spend / impressions × 1000` | Стоимость 1000 показов |

Если `spend = 0`, используется `budget`. Если знаменатель = 0 → метрика не отображается.

---

## Документация

- **[docs/FAQ.md](docs/FAQ.md)** — полный технический FAQ: все таблицы БД, формулы, логика каждой вкладки, attribution, кэш, воркеры
- **[docs/wiki/](docs/wiki/)** — Wiki по отдельным экранам и фичам

---

## Тесты

```bash
cd backend
pytest tests/ -v
# 69 тестов: воронка, UTM, attribution SQL, report helpers
```

---

<div align="center">
<sub>Internal analytics platform · PostgreSQL · FastAPI · React · Redis</sub>
</div>
