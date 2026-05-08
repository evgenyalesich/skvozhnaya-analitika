# Monolith Split Plan

## Цель
Свести файлы >400 строк к модульной структуре и снизить риск регрессий.

## Целевая архитектура
- `api/router/*.py`
- `services/<domain>/*.py`
- `repositories/<domain>/*.py`
- `schemas/<domain>/*.py`

## Фазы
1. **Security + stability first** (уже начато):
   - закрыть admin endpoints, стабилизировать replication, метрики, DLQ.
2. **Reports decomposition**:
   - разбить `api/routers/reports.py` на:
     - `reports_funnel.py`
     - `reports_roistat.py`
     - `reports_touch.py`
     - `reports_raw.py`
   - общий wire-up оставить в `reports/__init__.py`.
3. **Repository split**:
   - `report_repository.py` разбить по use-case:
     - `repo_funnel.py`
     - `repo_roistat.py`
     - `repo_touch.py`
     - `repo_raw.py`
4. **Worker split**:
   - `worker/tasks.py` разделить на:
     - `jobs_sync.py`
     - `jobs_telegram.py`
     - `jobs_cache.py`
     - `scheduler.py`
5. **Guardrails**:
   - CI size-guard (добавлен),
   - лимиты на функции/файлы для нового кода.

## Правило миграции
- Не переносить все сразу.
- Каждый PR:
  - перенос 1 поддомена,
  - тесты и smoke-check,
  - без изменения бизнес-логики.
