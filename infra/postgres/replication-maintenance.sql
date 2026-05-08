-- Safe slot maintenance helpers.

-- 1) See heavy and inactive logical slots
SELECT
  slot_name,
  database,
  active,
  inactive_since,
  pg_size_pretty(COALESCE(pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn), 0)) AS retained_wal,
  COALESCE(pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn), 0)::bigint AS retained_bytes
FROM pg_replication_slots
ORDER BY retained_bytes DESC;

-- 2) Generate DROP statements only for inactive analytics_* slots older than 30 minutes
SELECT format('SELECT pg_drop_replication_slot(%L);', slot_name) AS drop_sql
FROM pg_replication_slots
WHERE NOT active
  AND slot_name LIKE 'analytics_%'
  AND inactive_since < now() - interval '30 minutes';
