# Сквозная аналитика MVP

Этот репозиторий содержит каркас внутреннего сервиса сквозной аналитики маркетинга. Основные компоненты:

- `backend/` — FastAPI, модели, миграции, ingestion и отчеты
- `frontend/` — React + MUI интерфейс с Overview и RAW Users
- `config/` — YAML-конфиги для ботов, рекламных компаний и источников данных
- `infra/` — скрипты и описания для локального и docker-compose запуска

## Первые шаги
1. Заполнить конфигурацию источников и переменные окружения
   - `POSTGRES_ADMIN_DSN` нужен для подключения к PostgreSQL-серверу, списаний баз и динамического формирования DSN`ов для каждого бота (`config/bots.yaml` теперь хранит только `database_name`)
   - `ANALYTICS_DB_DSN` остаётся отдельной аналитической базой с таблицами `raw_bot_users`, `agg_daily_new_users` и т.д.
2. Настроить аналитическую базу данных (PostgreSQL)
3. Запустить ingestion и агрегаты
4. Поднять FastAPI и подключить фронтенд
5. Подключить мониторинг, логирование и документировать API

## Как запустить
- `backend`: `pip install -r backend/requirements.txt`, заполнить `.env`, запуск `uvicorn app.main:app --reload --host 0.0.0.0 --port 8000`
- `frontend`: `npm install` в каталоге `frontend/`, `npm run dev` (Vite доступен на `http://localhost:4173`)

## Переменные окружения
- `ANALYTICS_DB_DSN` — DSN аналитической базы, куда пишутся `raw_bot_users`, `agg_daily_new_users` и кэшируются отчёты.
- `POSTGRES_ADMIN_DSN` — единая точка входа к PostgreSQL‑серверу (обычно `postgres` или `template1`), из которой мы получаем список баз и подставляем их в ingestion для каждого `database_name` из `config/bots.yaml`.
- `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHANNEL_ID`, `TELEGRAM_COMMUNITY_ID` — используются Telegram API для проверок подписки/участия пользователей в канале и сообществе, чтобы пополнить статусы в `raw_bot_users`.
- `GOOGLE_SHEETS_CREDENTIALS_PATH`, `GOOGLE_SHEET_INTERVIEWS_ID` — сервисный ключ и ID таблицы с интервью/офферами/контрактами, чтобы подтягивать статусы `interview_reached`, `offer_received` и `contract_signed` через Google Sheets API.

## Ingestion и агрегаты
- Конфигурация ботов (`config/bots.yaml`) содержит переменные окружения с DSN для каждой PostgreSQL базы. Ингестия выполняет инкрементальный `upsert` по `(bot_key, tg_user_id)` в `raw_bot_users`.
- Сканирование и агрегация запускаются через RQ-задачи, которые обновляют `agg_daily_new_users` и кэшируют расчёты в Redis (TTL настраивается `CACHE_TTL_SECONDS`).
- Полезные команды:
  ```bash
  python -c "from app.worker.tasks import run_ingestion_job; run_ingestion_job()"
  python -c "from app.worker.tasks import run_aggregation_job; run_aggregation_job(days=90)"
  ```
- Для автоматического обновления поднять `rq worker -u $REDIS_URL default` и вызывать `schedule_ingestion_job()`/`schedule_aggregation_job()` (например, по cron/periodic task).
- `/api/reports` читает кэшированные значения (`reports:total`, `reports:daily`, `reports:breakdown:utm_source`, `reports:breakdown:utm_campaign`, `reports:breakdown:advertising_company`). Если кэш пустой или устарел, маршрут сам пересчитывает данные по базе и обновляет Redis, так что UI всегда обращается только к этим endpoint-ам.
- Раздел `/api/admin` теперь позволяет исследовать подключённые PostgreSQL-базы:
  - `GET /api/admin/databases` перебирает все пользовательские базы (`pg_database`).
  - `POST /api/admin/query-db` принимает JSON `{ "database": "...", "query": "SELECT ...", "limit": 100 }`, выполняет запрос (только `SELECT`, без `;`) и возвращает строки.
- Источники данных:
  - **PostgreSQL боты**: каждый конфиг в `config/bots.yaml` привязан к DSN через `BOT_*_DSN`.
  - **PokerHub Admin DB**: `data_sources.postgres_pokerhub.dsn_env`.
  - **Google Sheets**: `GOOGLE_SHEETS_CREDENTIALS_PATH` + `GOOGLE_SHEET_INTERVIEWS_ID` (содержит интервью/офферы/контракты).
  - **MongoDB**: `MONGODB_CONNECTION_STRING` с базой `pokerhub` и коллекцией `user_status` (team/internal статусы).
  - **Telegram API**: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHANNEL_ID`, `TELEGRAM_COMMUNITY_ID` для статусов подписки/участия.
  - **Рекламные платформы**: `config/advertising_companies.yaml` может хранить `manual_budgets`; агрегатор распределяет бюджет по пользователям и обновляет `RawBotUser.budget`.
