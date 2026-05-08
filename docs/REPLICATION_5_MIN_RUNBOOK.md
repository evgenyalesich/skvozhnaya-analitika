# Replication 5-Minute Runbook

## 1) Проверка симптома (1 минута)
- API жив: `curl -fsS http://127.0.0.1:9000/api/health`
- Потоки репликации: `GET /api/admin/replication/metrics`
- Слоты и WAL lag: `GET /api/admin/replication/slots`
- Очереди RQ: `GET /api/admin/status`

## 2) Быстрый стоп утечки WAL (1 минута)
- Посмотреть самые тяжелые слоты:
  - `SELECT slot_name, active, pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn)::bigint AS wal_bytes FROM pg_replication_slots ORDER BY wal_bytes DESC;`
- Если слот неактивен и раздувает WAL:
  - `SELECT pg_drop_replication_slot('<slot_name>');`
  - Поток пересоздаст слот автоматически.
- Безопасный вариант через SQL-шаблон:
  - запустить `infra/postgres/replication-maintenance.sql`
  - выполнить только `drop_sql` для `inactive analytics_*`.

## 3) Быстрый рестарт сервисов (1 минута)
- `sudo systemctl restart analytic-backend.service`
- `sudo systemctl restart analytic-worker-default.service`
- `sudo systemctl restart analytic-worker-telegram.service`

## 4) Проверка восстановления (1 минута)
- В `replication/metrics` должен быть `status=streaming`, `updated_at` свежий.
- В `replication/slots` retained_wal должен падать.
- В `sync-status` обновляется `last_ingestion_success`.

## 5) Если не восстановилось (1 минута)
- Проверить DLQ:
  - `SELECT * FROM replication_dlq ORDER BY created_at DESC LIMIT 100;`
- Проверить последние ошибки воркеров:
  - `journalctl -u analytic-backend.service -n 200 --no-pager`
  - `journalctl -u analytic-worker-default.service -n 200 --no-pager`
  - `journalctl -u analytic-replication-guard.service -n 200 --no-pager`

## Профилактика
- Применить `infra/postgres/replication-hardening.sql`.
- Включить `analytic-replication-guard.timer`.
- Включить `infra/logrotate/analytic-system` и `infra/journald/analytic-system.conf`.
- Включить `analytic-healthcheck.timer`.
