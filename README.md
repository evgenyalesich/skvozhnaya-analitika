# Сквозная аналитика MVP

Этот репозиторий содержит каркас внутреннего сервиса сквозной аналитики маркетинга. Основные компоненты:

- `backend/` — FastAPI, модели, миграции, ingestion и отчеты
- `frontend/` — React + MUI интерфейс с Overview и RAW Users
- `config/` — YAML-конфиги для ботов, рекламных компаний и источников данных
- `infra/` — скрипты и описания для локального и docker-compose запуска

## Первые шаги
1. Заполнить конфигурацию источников и переменные окружения
2. Настроить аналитическую базу данных (PostgreSQL)
3. Запустить ingestion и агрегаты
4. Поднять FastAPI и подключить фронтенд
5. Подключить мониторинг, логирование и документировать API

## Как запустить
- `backend`: `pip install -r backend/requirements.txt`, заполнить `.env`, запуск `uvicorn app.main:app --reload --host 0.0.0.0 --port 8000`
- `frontend`: `npm install` в каталоге `frontend/`, `npm run dev` (Vite доступен на `http://localhost:4173`)

## Ingestion и агрегаты
- Конфигурация ботов (`config/bots.yaml`) содержит переменные окружения с DSN для каждой PostgreSQL базы. Ингестия выполняет инкрементальный `upsert` по `(bot_key, tg_user_id)` в таблицу `raw_bot_users`.
- Для запуска ingestion вручную:
  ```bash
  python -c "from app.worker.tasks import run_ingestion_job; run_ingestion_job()"
  ```
- Для пересчёта агрегатов и заполнения Redis (TTL настраивается через `CACHE_TTL_SECONDS`):
  ```bash
  python -c "from app.worker.tasks import run_aggregation_job; run_aggregation_job(days=90)"
  ```
- Чтобы использовать фоновую очередь, запустите `rq worker -u $REDIS_URL default` и отправляйте задачи через `schedule_ingestion_job()`/`schedule_aggregation_job()`.
- Кэшированные данные доступны по ключам `reports:total`, `reports:daily`, `reports:breakdown`; `/api/reports` можно расширить, чтобы сначала читать Redis, потом базу.
