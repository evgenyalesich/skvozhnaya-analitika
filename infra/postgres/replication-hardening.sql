-- Apply in postgres as superuser, then reload/restart PostgreSQL.
-- Goal: keep logical replication stable and cap WAL growth from inactive slots.

ALTER SYSTEM SET wal_level = 'logical';
ALTER SYSTEM SET max_replication_slots = '128';
ALTER SYSTEM SET max_wal_senders = '128';
ALTER SYSTEM SET wal_sender_timeout = '60s';
ALTER SYSTEM SET idle_replication_slot_timeout = '10min';
ALTER SYSTEM SET max_slot_wal_keep_size = '8GB';
ALTER SYSTEM SET wal_keep_size = '1GB';
ALTER SYSTEM SET wal_compression = 'on';
ALTER SYSTEM SET log_checkpoints = 'on';
ALTER SYSTEM SET checkpoint_timeout = '10min';

SELECT pg_reload_conf();

-- Monitoring query for slot lag (run regularly):
-- SELECT slot_name, database, active,
--        pg_size_pretty(pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn)) AS retained_wal,
--        inactive_since
-- FROM pg_replication_slots
-- ORDER BY pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn) DESC;
