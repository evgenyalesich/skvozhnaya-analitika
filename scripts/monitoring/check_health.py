#!/usr/bin/env python3
import json
import os
import shutil
import sys
import time
from dataclasses import dataclass
from typing import Any

import psycopg2
from redis import Redis


@dataclass
class CheckResult:
    name: str
    ok: bool
    details: dict[str, Any]


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _check_disk() -> CheckResult:
    threshold = _env_int("ALERT_DISK_USED_PCT", 85)
    usage = shutil.disk_usage("/")
    used_pct = int((usage.used / max(1, usage.total)) * 100)
    return CheckResult(
        name="disk",
        ok=used_pct < threshold,
        details={"used_pct": used_pct, "threshold_pct": threshold},
    )


def _check_memory() -> CheckResult:
    threshold = _env_int("ALERT_MEM_USED_PCT", 92)
    mem_total = 0
    mem_available = 0
    with open("/proc/meminfo", "r", encoding="utf-8") as fh:
        for line in fh:
            if line.startswith("MemTotal:"):
                mem_total = int(line.split()[1]) * 1024
            elif line.startswith("MemAvailable:"):
                mem_available = int(line.split()[1]) * 1024
    used_pct = int(((mem_total - mem_available) / max(1, mem_total)) * 100) if mem_total else 0
    return CheckResult(
        name="memory",
        ok=used_pct < threshold,
        details={"used_pct": used_pct, "threshold_pct": threshold},
    )


def _check_redis_queues(redis_url: str) -> CheckResult:
    threshold = _env_int("ALERT_RQ_QUEUE_SIZE", 5000)
    queue_names = [q.strip() for q in os.getenv("ALERT_RQ_QUEUES", "default,telegram").split(",") if q.strip()]
    client = Redis.from_url(redis_url)
    sizes: dict[str, int] = {}
    for queue_name in queue_names:
        sizes[queue_name] = int(client.llen(f"rq:queue:{queue_name}") or 0)
    max_size = max(sizes.values()) if sizes else 0
    return CheckResult(
        name="rq_queues",
        ok=max_size < threshold,
        details={"sizes": sizes, "threshold": threshold},
    )


def _check_replication_slots(postgres_admin_dsn: str) -> CheckResult:
    threshold_mb = _env_int("ALERT_SLOT_RETAINED_WAL_MB", 2048)
    conn = psycopg2.connect(postgres_admin_dsn.replace("postgresql+asyncpg://", "postgresql://"))
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT
                slot_name,
                COALESCE(pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn)::bigint, 0) AS retained_wal_bytes
            FROM pg_replication_slots
            """
        )
        rows = cur.fetchall()
    finally:
        conn.close()
    slots = []
    max_mb = 0
    for name, bytes_value in rows:
        retained_mb = int((bytes_value or 0) / (1024 * 1024))
        max_mb = max(max_mb, retained_mb)
        slots.append({"slot_name": name, "retained_mb": retained_mb})
    return CheckResult(
        name="replication_slots",
        ok=max_mb < threshold_mb,
        details={"slots": slots, "max_retained_mb": max_mb, "threshold_mb": threshold_mb},
    )


def _check_replication_stream_metrics(redis_url: str) -> CheckResult:
    stale_seconds = _env_int("ALERT_REPL_METRICS_STALE_SECONDS", 180)
    client = Redis.from_url(redis_url)
    stream_keys = client.keys("replication:stream:*:metrics")
    now_ts = int(time.time())
    stale_streams = []
    for key in stream_keys:
        raw = client.get(key)
        if not raw:
            continue
        try:
            payload = json.loads(raw)
        except Exception:
            continue
        updated_at = int(payload.get("updated_at") or 0)
        if now_ts - updated_at > stale_seconds:
            stale_streams.append(payload.get("db_name") or str(key))
    return CheckResult(
        name="replication_stream_metrics",
        ok=len(stale_streams) == 0,
        details={"stale_streams": stale_streams, "stale_seconds": stale_seconds, "streams_total": len(stream_keys)},
    )


def main() -> int:
    redis_url = os.getenv("REDIS_URL")
    postgres_admin_dsn = os.getenv("POSTGRES_ADMIN_DSN")
    checks: list[CheckResult] = []

    checks.append(_check_disk())
    checks.append(_check_memory())
    if redis_url:
        checks.append(_check_redis_queues(redis_url))
        checks.append(_check_replication_stream_metrics(redis_url))
    if postgres_admin_dsn:
        checks.append(_check_replication_slots(postgres_admin_dsn))

    failures = [c for c in checks if not c.ok]
    payload = {
        "ok": len(failures) == 0,
        "checks": [{"name": c.name, "ok": c.ok, "details": c.details} for c in checks],
    }
    print(json.dumps(payload, ensure_ascii=False))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
