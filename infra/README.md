# Инфраструктура

## Что добавлено
- `infra/systemd/*.service` и `*.timer`: backend/worker/health-check юниты.
- `infra/logrotate/analytic-system`: ротация runtime логов.
- `infra/journald/analytic-system.conf`: лимиты journald, чтобы не съедать диск.
- `infra/postgres/replication-hardening.sql`: ограничения WAL/slot retention.
- `infra/postgres/replication-maintenance.sql`: безопасные SQL для ревизии/очистки слотов.
- `infra/systemd/analytic-replication-guard.*`: таймер-сторож слотов и WAL.
- `scripts/monitoring/replication_guard.py`: dry-run guard (опционально auto-drop неактивных слотов).

## Быстрый деплой (Linux/systemd)
1. Скопировать юниты:
   - `sudo cp infra/systemd/*.service /etc/systemd/system/`
   - `sudo cp infra/systemd/*.timer /etc/systemd/system/`
2. Включить сервисы:
   - `sudo systemctl daemon-reload`
   - `sudo systemctl enable --now analytic-backend.service`
   - `sudo systemctl enable --now analytic-worker-default.service`
   - `sudo systemctl enable --now analytic-worker-telegram.service`
   - `sudo systemctl enable --now analytic-healthcheck.timer`
   - `sudo systemctl enable --now analytic-replication-guard.timer`
3. Включить logrotate:
   - `sudo cp infra/logrotate/analytic-system /etc/logrotate.d/analytic-system`
4. Включить journald лимиты:
   - `sudo cp infra/journald/analytic-system.conf /etc/systemd/journald.conf.d/analytic-system.conf`
   - `sudo systemctl restart systemd-journald`
5. Применить PostgreSQL hardening:
   - выполнить `infra/postgres/replication-hardening.sql` под superuser.
6. Ручной чек слотов:
   - выполнить `infra/postgres/replication-maintenance.sql`

## Мониторинг
- runtime health script: `scripts/monitoring/check_health.py`
- replication guard: `scripts/monitoring/replication_guard.py`
- incident runbook: `docs/REPLICATION_5_MIN_RUNBOOK.md`

## Рекомендованные env для guard
- `REPL_GUARD_MAX_SLOT_MB=4096`
- `REPL_GUARD_INACTIVE_MINUTES=30`
- `REPL_GUARD_SLOT_PREFIX=analytics_`
- `REPL_GUARD_DROP_INACTIVE=false` (включать `true` только после dry-run и в окне обслуживания)
