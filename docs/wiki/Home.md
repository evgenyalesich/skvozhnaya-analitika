# Главная

Эта wiki описывает текущее состояние проекта `analytic-system` после рефакторинга backend на `*_parts`/`*_runtime` модули.

С чего начинать:

- `System-Architecture` — общая архитектура, точки входа, runtime-компоненты.
- `Data-Flow-and-DB` — сбор данных, таблицы PostgreSQL, кто пишет в БД и кто читает.
- `Roistat-File-Map` — актуальная карта файлов frontend/backend.
- `Roistat-Weekly` — текущая логика Weekly-отчёта.
- `Roistat-Troubleshooting` — диагностика и типовые сбои.

Быстрые ссылки по продуктовым разделам:

- `Roistat-Overview`
- `Roistat-Funnel`
- `Roistat-TotalA`
- `Roistat-TotalB`
- `Roistat-TotalC`
- `Roistat-TG-Subs`
- `Roistat-RAW-Users`
- `Roistat-RAW-UTM`
- `Roistat-Main-Report-Columns`
- `Roistat-Auth`

Что важно знать заранее:

- Основная операционная таблица проекта — `raw_bot_users`.
- Основное зеркало платформы PokerHub — `ph_user_mirror_replica`.
- Большинство витрин считаются либо напрямую из `raw_bot_users`, либо из специализированных SQL-срезов поверх неё.
- Старые монолитные файлы в `backend/app/services/*.py`, `backend/app/api/routers/*.py`, `backend/app/worker/*.py` часто оставлены как compatibility facade и переадресуют в новые `*_parts`/`runtime` модули.
